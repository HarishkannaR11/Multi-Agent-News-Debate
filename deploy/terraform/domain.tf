# Optional: serve the site on your own domain name (var.domain_name) instead of dxxxx.cloudfront.net.
#
# It takes two applies, because CloudFront can only use a certificate that is already validated:
#   apply 1 (attach_domain = false): creates the HTTPS certificate (and the Route 53 zone when asked) and
#            prints the DNS records you must create.
#   apply 2 (attach_domain = true):  waits for the certificate, attaches the domain to CloudFront and, with
#            Route 53, creates the records that point the domain at it.

locals {
  # True when a domain name was given.
  use_domain = var.domain_name != ""
  # Every address the site answers on (the main one first).
  hostnames = local.use_domain ? concat([var.domain_name], var.extra_domain_names) : []
  # True once the second step has been requested: only then does CloudFront get the domain and certificate.
  attach = local.use_domain && var.attach_domain
  # True when AWS Route 53 hosts the DNS records.
  use_route53 = local.use_domain && var.dns_provider == "route53"
  # The DNS zone Route 53 will host (normally the main domain, even when the site is on a subdomain).
  zone_name = var.route53_zone_name != "" ? var.route53_zone_name : var.domain_name
}

# --- the HTTPS certificate ---------------------------------------------------------------------------------------

# A free certificate from AWS Certificate Manager. CloudFront only accepts certificates from us-east-1,
# hence the second provider. "DNS" validation means: you prove you own the domain by creating a DNS record.
resource "aws_acm_certificate" "site" {
  count    = local.use_domain ? 1 : 0
  provider = aws.us_east_1

  domain_name               = var.domain_name
  subject_alternative_names = var.extra_domain_names
  validation_method         = "DNS"

  lifecycle {
    create_before_destroy = true
  }
}

locals {
  # The DNS records that prove ownership, one per address: { name, type, value }.
  validation_records = local.use_domain ? {
    for option in aws_acm_certificate.site[0].domain_validation_options : option.domain_name => {
      name  = option.resource_record_name
      type  = option.resource_record_type
      value = option.resource_record_value
    }
  } : {}
}

# --- Route 53 (only with dns_provider = "route53") ------------------------------------------------------------------

# The DNS zone AWS will host for your domain. After the first apply you must tell your registrar to use its
# name servers (see the route53_nameservers output).
resource "aws_route53_zone" "site" {
  count = local.use_route53 ? 1 : 0
  name  = local.zone_name
}

# The validation records, created automatically.
resource "aws_route53_record" "validation" {
  for_each = local.use_route53 ? local.validation_records : {}

  zone_id         = aws_route53_zone.site[0].zone_id
  name            = each.value.name
  type            = each.value.type
  records         = [each.value.value]
  ttl             = 60
  allow_overwrite = true
}

# --- step 2: use the certificate -------------------------------------------------------------------------------------

# Waits until AWS has checked the validation records and issued the certificate. This is what makes the
# second apply "hang" for a while if the DNS records are missing or have not spread yet.
resource "aws_acm_certificate_validation" "site" {
  count    = local.attach ? 1 : 0
  provider = aws.us_east_1

  certificate_arn         = aws_acm_certificate.site[0].arn
  validation_record_fqdns = local.use_route53 ? [for record in aws_route53_record.validation : record.fqdn] : null
}

# Point each address at CloudFront (IPv4 "A" and IPv6 "AAAA" alias records).
resource "aws_route53_record" "site_a" {
  for_each = local.attach && local.use_route53 ? toset(local.hostnames) : toset([])

  zone_id = aws_route53_zone.site[0].zone_id
  name    = each.value
  type    = "A"

  alias {
    name                   = aws_cloudfront_distribution.site.domain_name
    zone_id                = aws_cloudfront_distribution.site.hosted_zone_id
    evaluate_target_health = false
  }
}

resource "aws_route53_record" "site_aaaa" {
  for_each = local.attach && local.use_route53 ? toset(local.hostnames) : toset([])

  zone_id = aws_route53_zone.site[0].zone_id
  name    = each.value
  type    = "AAAA"

  alias {
    name                   = aws_cloudfront_distribution.site.domain_name
    zone_id                = aws_cloudfront_distribution.site.hosted_zone_id
    evaluate_target_health = false
  }
}
