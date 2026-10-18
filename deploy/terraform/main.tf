# The whole stack: one EC2 server running Redis + backend + frontend + Caddy (Docker Compose) behind
# CloudFront (HTTPS), plus alarms, disk snapshots, a budget alert and an optional firewall.
# It mirrors deploy/aws/cloudformation.yaml; see docs/DEPLOY_TERRAFORM.md.

# --- lookups -------------------------------------------------------------------------------------------

# The region the main provider uses (its name builds the server's public DNS name below).
data "aws_region" "current" {}

# The region's default network: the server and its firewall live there (like the CloudFormation version).
data "aws_vpc" "default" {
  default = true
}

# The newest Ubuntu 24.04 LTS image id for this region, published by Canonical in Systems Manager.
data "aws_ssm_parameter" "ubuntu" {
  name = "/aws/service/canonical/ubuntu/server/24.04/stable/current/amd64/hvm/ebs-gp3/ami-id"
}

locals {
  # AWS-managed CloudFront policies, referenced by their fixed ids.
  cache_policy_disabled  = "4135ea2d-6df8-44a3-9df3-4b5a84be39ad" # Managed-CachingDisabled
  cache_policy_optimized = "658327ea-f89d-4fab-a63d-7e88639e58f6" # Managed-CachingOptimized
  origin_policy_all      = "216adef6-5c7f-47e4-b989-5492eafa07d3" # Managed-AllViewer (forwards X-Forwarded-For etc.)

  # The Elastic IP's public DNS name: ec2-<a>-<b>-<c>-<d>.compute-1.amazonaws.com in us-east-1,
  # ec2-<a>-<b>-<c>-<d>.<region>.compute.amazonaws.com everywhere else. CloudFront needs a name, not an IP.
  origin_domain = format(
    "ec2-%s.%s.amazonaws.com",
    replace(aws_eip.server.public_ip, ".", "-"),
    data.aws_region.current.name == "us-east-1" ? "compute-1" : "${data.aws_region.current.name}.compute"
  )
}

# --- secrets: kept out of the instance's user data; the server reads them at boot ---------------------------

resource "aws_secretsmanager_secret" "app" {
  name        = "${var.name}-app-secrets"
  description = "Counterpoint API keys and admin token"
  # Delete immediately on `terraform destroy`, so the same name can be used again right away.
  recovery_window_in_days = 0
}

resource "aws_secretsmanager_secret_version" "app" {
  secret_id = aws_secretsmanager_secret.app.id
  # A JSON object of KEY = value pairs; bootstrap.sh turns it into the server's .env file.
  secret_string = jsonencode({
    GROQ_API_KEY  = var.groq_api_key
    NEWSAPI_KEY   = var.newsapi_key
    GNEWS_API_KEY = var.gnews_api_key
    ADMIN_TOKEN   = var.admin_token
  })

  lifecycle {
    # The debate pipeline needs at least one news source.
    precondition {
      condition     = var.newsapi_key != "" || var.gnews_api_key != ""
      error_message = "Set newsapi_key or gnews_api_key (or both): the app needs a news source."
    }
  }
}

# --- access: no SSH. Use Session Manager (EC2 console -> Connect -> Session Manager) ---------------------------

# The identity the server uses when it talks to AWS (so no access keys are stored on it).
resource "aws_iam_role" "server" {
  name = "${var.name}-server"
  # Only the EC2 service may use this role.
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "ec2.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

# An AWS-made permission set that lets Session Manager (browser terminal, no SSH) work.
resource "aws_iam_role_policy_attachment" "ssm" {
  role       = aws_iam_role.server.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

# Read exactly one secret, and publish the one health metric; nothing else.
resource "aws_iam_role_policy" "server" {
  name = "app-access"
  role = aws_iam_role.server.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = "secretsmanager:GetSecretValue"
        Resource = aws_secretsmanager_secret.app.arn
      },
      {
        Effect    = "Allow"
        Action    = "cloudwatch:PutMetricData"
        Resource  = "*"
        Condition = { StringEquals = { "cloudwatch:namespace" = "Counterpoint" } }
      }
    ]
  })
}

# The wrapper that lets an EC2 server use the role.
resource "aws_iam_instance_profile" "server" {
  name = "${var.name}-server"
  role = aws_iam_role.server.name
}

# --- network: only HTTP in (CloudFront talks to the origin over HTTP) ----------------------------------------

resource "aws_security_group" "server" {
  name        = "${var.name}-server"
  description = "Counterpoint server - HTTP only, no SSH"
  vpc_id      = data.aws_vpc.default.id

  ingress {
    description = "HTTP (from CloudFront)"
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  # Allow the server to reach the internet (package downloads, Docker images, Groq, news APIs, AWS APIs).
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

# --- the server ----------------------------------------------------------------------------------------------

resource "aws_instance" "server" {
  ami                    = data.aws_ssm_parameter.ubuntu.value
  instance_type          = var.instance_type
  iam_instance_profile   = aws_iam_instance_profile.server.name
  vpc_security_group_ids = [aws_security_group.server.id]

  # 30 GB of fast (gp3) storage that is deleted together with the server.
  root_block_device {
    volume_size           = 30
    volume_type           = "gp3"
    delete_on_termination = true
    encrypted             = true
  }

  # Require the safer token-based version of the instance metadata service (IMDSv2).
  metadata_options {
    http_tokens   = "required"
    http_endpoint = "enabled"
  }

  # The first-boot script. The secrets themselves are NOT in it, only the secret's name.
  user_data = templatefile("${path.module}/user_data.sh.tftpl", {
    secret_id = aws_secretsmanager_secret.app.id
    region    = data.aws_region.current.name
    git_ref   = var.git_ref
    repo_url  = var.repo_url
  })
  # Changing the script later does not replace a running server (use update.sh on the server instead).
  user_data_replace_on_change = false

  tags = {
    Name = var.name
    # The snapshot schedule below selects servers by this tag.
    Backup = "counterpoint"
  }

  # The secret must hold its value before the server boots and reads it.
  depends_on = [aws_secretsmanager_secret_version.app]
}

# A fixed address, so stopping and starting the server (to save credits) does not break CloudFront.
resource "aws_eip" "server" {
  domain = "vpc"
  tags   = { Name = var.name }
}

resource "aws_eip_association" "server" {
  allocation_id = aws_eip.server.id
  instance_id   = aws_instance.server.id
}

# --- HTTPS in front: CloudFront default domain, WebSockets work, nothing cached for the app -----------------

# Optional firewall (enable_waf = true). Must be in us-east-1 for CloudFront, hence the second provider.
resource "aws_wafv2_web_acl" "main" {
  count    = var.enable_waf ? 1 : 0
  provider = aws.us_east_1

  name  = "${var.name}-waf"
  scope = "CLOUDFRONT"

  # Allow requests unless a rule below blocks them.
  default_action {
    allow {}
  }

  visibility_config {
    cloudwatch_metrics_enabled = true
    sampled_requests_enabled   = true
    metric_name                = "${var.name}-waf"
  }

  # Rule 1: block an IP address that sends more than 1000 requests in 5 minutes.
  rule {
    name     = "rate-limit-per-ip"
    priority = 1

    action {
      block {}
    }

    statement {
      rate_based_statement {
        limit              = 1000
        aggregate_key_type = "IP"
      }
    }

    visibility_config {
      cloudwatch_metrics_enabled = true
      sampled_requests_enabled   = true
      metric_name                = "${var.name}-rate-limit"
    }
  }

  # Rule 2: AWS's maintained rules against common web attacks.
  rule {
    name     = "aws-common-rules"
    priority = 2

    override_action {
      none {}
    }

    statement {
      managed_rule_group_statement {
        vendor_name = "AWS"
        name        = "AWSManagedRulesCommonRuleSet"
      }
    }

    visibility_config {
      cloudwatch_metrics_enabled = true
      sampled_requests_enabled   = true
      metric_name                = "${var.name}-common-rules"
    }
  }
}

resource "aws_cloudfront_distribution" "site" {
  enabled      = true
  comment      = var.name
  http_version = "http2"
  # Let visitors on IPv6 networks connect too (needed for the AAAA records of your own domain).
  is_ipv6_enabled = true
  # Use only the cheapest set of edge locations (North America and Europe).
  price_class = "PriceClass_100"
  # Attach the firewall when it was requested.
  web_acl_id = var.enable_waf ? aws_wafv2_web_acl.main[0].arn : null

  # The "origin" is where CloudFront fetches content from: our server.
  origin {
    origin_id   = "server"
    domain_name = local.origin_domain

    # CloudFront connects to our server over plain HTTP on port 80, waiting up to 60 seconds for answers.
    custom_origin_config {
      origin_protocol_policy   = "http-only"
      http_port                = 80
      https_port               = 443
      origin_ssl_protocols     = ["TLSv1.2"]
      origin_read_timeout      = 60
      origin_keepalive_timeout = 60
    }
  }

  # The default rule for every request: no caching, all headers forwarded, all methods allowed (the API needs POST).
  default_cache_behavior {
    target_origin_id         = "server"
    viewer_protocol_policy   = "redirect-to-https"
    allowed_methods          = ["GET", "HEAD", "OPTIONS", "PUT", "POST", "PATCH", "DELETE"]
    cached_methods           = ["GET", "HEAD"]
    compress                 = true
    cache_policy_id          = local.cache_policy_disabled
    origin_request_policy_id = local.origin_policy_all
  }

  # Content-hashed build assets never change, so they are safe to cache.
  ordered_cache_behavior {
    path_pattern           = "/_next/static/*"
    target_origin_id       = "server"
    viewer_protocol_policy = "redirect-to-https"
    allowed_methods        = ["GET", "HEAD"]
    cached_methods         = ["GET", "HEAD"]
    compress               = true
    cache_policy_id        = local.cache_policy_optimized
  }

  restrictions {
    geo_restriction {
      restriction_type = "none"
    }
  }

  # Your own domain (set after the certificate is validated; see domain.tf).
  aliases = local.attach ? local.hostnames : []

  # Without a custom domain: the free default https://dxxxx.cloudfront.net certificate.
  # With one: the validated certificate from AWS Certificate Manager.
  viewer_certificate {
    cloudfront_default_certificate = local.attach ? null : true
    acm_certificate_arn            = local.attach ? aws_acm_certificate_validation.site[0].certificate_arn : null
    ssl_support_method             = local.attach ? "sni-only" : null
    minimum_protocol_version       = local.attach ? "TLSv1.2_2021" : null
  }

  # The origin's DNS name only exists once the address is attached to the server.
  depends_on = [aws_eip_association.server]

  lifecycle {
    precondition {
      condition     = !var.attach_domain || var.domain_name != ""
      error_message = "attach_domain = true needs domain_name to be set."
    }
    precondition {
      condition     = var.dns_provider != "route53" || var.domain_name == "" || endswith(var.domain_name, local.zone_name)
      error_message = "route53_zone_name must be your domain or its parent, e.g. krisharish.space for krisharish.space or www.krisharish.space."
    }
  }
}

# --- backups: daily snapshots of the server's disk, keeping the last 3 ----------------------------------------

# The permission the snapshot scheduler uses (AWS-managed policy).
resource "aws_iam_role" "snapshots" {
  name = "${var.name}-snapshots"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "dlm.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy_attachment" "snapshots" {
  role       = aws_iam_role.snapshots.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSDataLifecycleManagerServiceRole"
}

# Data Lifecycle Manager: snapshots every disk of servers tagged Backup=counterpoint.
resource "aws_dlm_lifecycle_policy" "snapshots" {
  description        = "Daily snapshots of the Counterpoint server disk"
  execution_role_arn = aws_iam_role.snapshots.arn
  state              = "ENABLED"

  policy_details {
    resource_types = ["INSTANCE"]
    target_tags    = { Backup = "counterpoint" }

    schedule {
      name = "daily"

      create_rule {
        interval      = 24
        interval_unit = "HOURS"
        times         = ["03:00"]
      }

      retain_rule {
        count = 3
      }

      copy_tags = true
    }
  }
}

# --- monitoring: one email when the site looks unhealthy ---------------------------------------------------------

# Where alarm messages go; AWS emails alert_email a "confirm subscription" message the first time.
resource "aws_sns_topic" "alarms" {
  name = "${var.name}-alarms"
}

resource "aws_sns_topic_subscription" "email" {
  topic_arn = aws_sns_topic.alarms.arn
  protocol  = "email"
  endpoint  = var.alert_email
}

# Fires when the 5-minute health check (deploy/aws/healthcheck.sh) reports a problem for 15 minutes in a row:
# the backend is not ready, or no new debate has been created for 36 hours.
resource "aws_cloudwatch_metric_alarm" "health" {
  alarm_name          = "${var.name}-health"
  alarm_description   = "Counterpoint backend is not ready, or the daily debate is missing."
  namespace           = "Counterpoint"
  metric_name         = "Healthy"
  statistic           = "Minimum"
  period              = 300
  evaluation_periods  = 3
  threshold           = 1
  comparison_operator = "LessThanThreshold"
  # No data (for example while the server is deliberately stopped to save credits) is not an alarm.
  treat_missing_data = "notBreaching"
  alarm_actions      = [aws_sns_topic.alarms.arn]
}

# Fires when AWS itself says the virtual machine is broken (hardware or network failure).
resource "aws_cloudwatch_metric_alarm" "server_status" {
  alarm_name          = "${var.name}-server-status"
  alarm_description   = "The EC2 status checks for the Counterpoint server are failing."
  namespace           = "AWS/EC2"
  metric_name         = "StatusCheckFailed"
  dimensions          = { InstanceId = aws_instance.server.id }
  statistic           = "Maximum"
  period              = 60
  evaluation_periods  = 5
  threshold           = 1
  comparison_operator = "GreaterThanOrEqualToThreshold"
  treat_missing_data  = "notBreaching"
  alarm_actions       = [aws_sns_topic.alarms.arn]
}

# --- cost guard-rail ------------------------------------------------------------------------------------------------

# A budget that emails a warning when spending gets close to the limit.
resource "aws_budgets_budget" "monthly" {
  name         = "${var.name}-monthly"
  budget_type  = "COST"
  time_unit    = "MONTHLY"
  limit_amount = tostring(var.monthly_budget_usd)
  limit_unit   = "USD"

  # 1) when the actual spending passes 80% of the limit
  notification {
    notification_type          = "ACTUAL"
    comparison_operator        = "GREATER_THAN"
    threshold                  = 80
    threshold_type             = "PERCENTAGE"
    subscriber_email_addresses = [var.alert_email]
  }

  # 2) when the forecast says the month will end above 100% of the limit
  notification {
    notification_type          = "FORECASTED"
    comparison_operator        = "GREATER_THAN"
    threshold                  = 100
    threshold_type             = "PERCENTAGE"
    subscriber_email_addresses = [var.alert_email]
  }
}
