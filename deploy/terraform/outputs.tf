output "site_url" {
  description = "Your site. Give the server 10-15 minutes after apply finishes."
  value       = "https://${aws_cloudfront_distribution.site.domain_name}"
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
