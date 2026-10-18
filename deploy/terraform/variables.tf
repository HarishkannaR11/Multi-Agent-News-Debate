# --- where ---------------------------------------------------------------------------------------

variable "aws_region" {
  type        = string
  default     = "us-east-1"
  description = "Region for the server and everything else. c7i-flex / m7i-flex sizes are not offered in every region."
}

variable "name" {
  type        = string
  default     = "counterpoint"
  description = "Name prefix for the resources."
}

# --- secrets (marked sensitive: hidden in plan output; they are still stored in the state file) ---

variable "groq_api_key" {
  type        = string
  sensitive   = true
  description = "Groq API key (console.groq.com)."

  validation {
    condition     = can(regex("^[A-Za-z0-9_-]{10,}$", var.groq_api_key))
    error_message = "The Groq key must be at least 10 characters: letters, digits, - and _ only."
  }
}

variable "newsapi_key" {
  type        = string
  sensitive   = true
  default     = ""
  description = "NewsAPI key. Provide this or gnews_api_key (or both)."

  validation {
    condition     = can(regex("^[A-Za-z0-9_-]*$", var.newsapi_key))
    error_message = "Letters, digits, - and _ only."
  }
}

variable "gnews_api_key" {
  type        = string
  sensitive   = true
  default     = ""
  description = "GNews key. Provide this or newsapi_key (or both)."

  validation {
    condition     = can(regex("^[A-Za-z0-9_-]*$", var.gnews_api_key))
    error_message = "Letters, digits, - and _ only."
  }
}

variable "admin_token" {
  type        = string
  sensitive   = true
  description = "A long random string that protects the 'generate debate' endpoint (at least 24 characters)."

  validation {
    condition     = can(regex("^[A-Za-z0-9_-]{24,}$", var.admin_token))
    error_message = "At least 24 characters: letters, digits, - and _ only. Generate one with: openssl rand -hex 24"
  }
}

# --- alerts and cost -------------------------------------------------------------------------------

variable "alert_email" {
  type        = string
  description = "Email that receives the health alarms and the budget warnings."

  validation {
    condition     = can(regex("^[^@\\s]+@[^@\\s]+\\.[^@\\s]+$", var.alert_email))
    error_message = "Enter a valid email address."
  }
}

variable "monthly_budget_usd" {
  type        = number
  default     = 40
  description = "Monthly spend (USD) that triggers the budget warning emails."

  validation {
    condition     = var.monthly_budget_usd >= 5
    error_message = "The budget must be at least 5 USD."
  }
}

# --- server and code ---------------------------------------------------------------------------------

variable "instance_type" {
  type        = string
  default     = "c7i-flex.large"
  description = "Needs 4 GB of RAM or more. On an AWS 'Free plan' account pick one the EC2 console marks 'Free tier eligible' in your region."

  validation {
    condition     = contains(["c7i-flex.large", "m7i-flex.large", "t3.medium", "t3.large"], var.instance_type)
    error_message = "Choose one of: c7i-flex.large, m7i-flex.large, t3.medium, t3.large."
  }
}

variable "repo_url" {
  type        = string
  default     = "https://github.com/HarishkannaR11/Multi-Agent-News-Debate.git"
  description = "Public Git repository to deploy."
}

variable "git_ref" {
  type        = string
  default     = "claude/exciting-faraday-lphld3"
  description = "Branch or tag to deploy. Use main only after the reviewed code has been merged into it."
}

variable "enable_waf" {
  type        = bool
  default     = false
  description = "Add an AWS WAF web ACL in front of CloudFront (rate limit per IP + AWS common rules). Roughly 8 USD a month."
}

# --- your own domain name (optional) -------------------------------------------------------------------------
# Leave domain_name empty to use the free https://dxxxx.cloudfront.net address. To use your own domain, follow
# docs/DEPLOY_TERRAFORM.md ("Use your own domain"): it takes two applies, because the HTTPS certificate must be
# validated by DNS before CloudFront can use it.

variable "domain_name" {
  type        = string
  default     = ""
  description = "The address to serve the site on, e.g. krisharish.space or debate.krisharish.space. Empty = use the CloudFront address."

  validation {
    condition     = var.domain_name == "" || can(regex("^([a-z0-9]([a-z0-9-]*[a-z0-9])?\\.)+[a-z]{2,}$", var.domain_name))
    error_message = "Use lower-case letters, digits, hyphens and dots, e.g. krisharish.space (no https://, no path)."
  }
}

variable "extra_domain_names" {
  type        = list(string)
  default     = []
  description = "Additional addresses for the same site, e.g. [\"www.krisharish.space\"]."

  validation {
    condition     = alltrue([for d in var.extra_domain_names : can(regex("^([a-z0-9]([a-z0-9-]*[a-z0-9])?\\.)+[a-z]{2,}$", d))])
    error_message = "Each extra name must look like www.krisharish.space (lower case, no https://, no path)."
  }
}

variable "dns_provider" {
  type        = string
  default     = "registrar"
  description = "Where the domain's DNS records live: \"registrar\" (you add 2 records by hand where you bought the domain) or \"route53\" (AWS hosts the DNS and Terraform adds the records; about 0.50 USD a month)."

  validation {
    condition     = contains(["registrar", "route53"], var.dns_provider)
    error_message = "dns_provider must be \"registrar\" or \"route53\"."
  }
}

variable "route53_zone_name" {
  type        = string
  default     = ""
  description = "Only for dns_provider = \"route53\": the DNS zone to create, normally your main domain (krisharish.space). Empty = same as domain_name."
}

variable "attach_domain" {
  type        = bool
  default     = false
  description = "Second step: false = only create the certificate (and DNS zone); true = attach the domain to CloudFront. Set it to true once the certificate shows as Issued."
}
