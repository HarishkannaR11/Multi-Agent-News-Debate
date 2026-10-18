output "site_url" {
  description = "Your site. Give the server 10-15 minutes after apply finishes."
  value       = "https://${local.attach ? var.domain_name : aws_cloudfront_distribution.site.domain_name}"
}

output "cloudfront_address" {
  description = "The CloudFront address (the site also answers here). With your own domain and dns_provider = registrar, point your domain at this name."
  value       = aws_cloudfront_distribution.site.domain_name
}

output "route53_nameservers" {
  description = "Only with dns_provider = route53: set these 4 name servers at your registrar (where you bought the domain)."
  value       = local.use_route53 ? aws_route53_zone.site[0].name_servers : []
}

output "dns_records_to_create_at_registrar" {
  description = "Only with dns_provider = registrar: the certificate-validation records to create where you manage DNS."
  value       = local.use_domain && !local.use_route53 ? values(local.validation_records) : []
}

output "health_check_url" {
  description = "Shows {\"status\":\"ready\"} once the backend is up."
  value       = "https://${aws_cloudfront_distribution.site.domain_name}/health/ready"
}

output "instance_id" {
  description = "Open this instance in the EC2 console and use Connect -> Session Manager to run commands."
  value       = aws_instance.server.id
}

output "server_ip" {
  description = "The server's fixed public address (an Elastic IP)."
  value       = aws_eip.server.public_ip
}

output "bootstrap_log_command" {
  description = "Command to follow the first-boot progress (run in Session Manager)."
  value       = "sudo tail -f /var/log/counterpoint-bootstrap.log"
}

output "check_site_command" {
  description = "Run this on your own computer once the site is up (needs curl, jq, python3 + websockets)."
  value       = "deploy/aws/check_site.sh https://${aws_cloudfront_distribution.site.domain_name}"
}
