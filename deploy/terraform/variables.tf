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
