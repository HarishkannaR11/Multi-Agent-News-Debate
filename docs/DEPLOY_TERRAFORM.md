# Deploy on AWS with Terraform

This builds the same stack as [`DEPLOY_AWS.md`](DEPLOY_AWS.md) (CloudFormation), from the files in
[`deploy/terraform/`](../deploy/terraform/): one EC2 server running Redis, the backend, the frontend
and Caddy with Docker Compose, behind CloudFront (HTTPS), plus health alarms, daily disk snapshots, a
budget alert and an optional firewall. **Use one method or the other, not both** (they create separate
copies of everything).

Read the cost section of [`DEPLOY_AWS.md`](DEPLOY_AWS.md) first: it is not free forever
(about 60–70 USD a month at the default size, so credits last roughly 1.5 months). `terraform destroy`
removes everything that charges.

## What has and has not been checked

Checked: `terraform fmt`, `terraform validate` (against AWS provider 5.99), the input validations
(bad keys, short admin token, bad size, bad email are rejected before anything is created), and the
first-boot script rendered from the template passes `bash -n` and shellcheck. CI runs fmt and validate on
every change.

**Not checked: a real `plan` or `apply`.** I have no AWS account to run them against, so the first
`terraform plan` on your account is the real test. The things most likely to need a small fix are the
ones that depend on your account: which instance sizes it allows, the region, and the budget/alarm
emails. If `apply` fails, send me the error text (never your keys) and I will fix it.

## What you need

- An AWS account with the credits, and permission to create EC2, IAM, CloudFront, Secrets Manager,
  SNS, CloudWatch, DLM and Budgets resources (an administrator user is simplest for a personal account).
- [Terraform](https://developer.hashicorp.com/terraform/install) 1.5 or newer.
- AWS credentials on your own computer, set up the way AWS recommends, for example `aws configure`
  or `aws sso login`. **Never paste access keys or the keys below into a chat.**
- A Groq API key, a NewsAPI and/or GNews key, and an admin token (`openssl rand -hex 24`).

## Steps

```bash
cd deploy/terraform
cp terraform.tfvars.example terraform.tfvars   # then edit it (it is git-ignored)
terraform init
terraform plan        # read it: about 19 resources (20 with the firewall), nothing is created yet
terraform apply       # type "yes"
```

Prefer not to write secrets to a file? Leave them out of `terraform.tfvars` and export them instead:

```bash
export TF_VAR_groq_api_key=...  TF_VAR_admin_token=...  TF_VAR_newsapi_key=...
```

Choose an `instance_type` your account may use (EC2 console → **Launch instance** lists the ones marked
*Free tier eligible*), and the region in `aws_region`.

After `apply` prints the outputs:

1. **Confirm the email subscription.** AWS emails `alert_email` a *Subscription Confirmation*; the
   health alarms stay silent until you click it.
2. **Wait 10–15 minutes** while the server builds the app. Follow it in the EC2 console →
   **Connect → Session Manager** with `sudo tail -f /var/log/counterpoint-bootstrap.log`
   (the `bootstrap_log_command` output).
3. Open `health_check_url` until it shows `{"status":"ready"}`.
4. From your own computer run the command in `check_site_command`. It checks HTTPS, the API, the
   protected admin route and a **WebSocket through CloudFront** (the one thing I could not test).
5. In Session Manager: `sudo /opt/counterpoint/app/deploy/aws/run-daily.sh` generates the first debate
   (a new one is created daily at 07:00 UTC after that). Then open `site_url`.

Everyday operations (updating, changing a key, logs, rotating the admin token) are the same as in
[`DEPLOY_AWS.md`](DEPLOY_AWS.md#everyday-operations-all-in-session-manager). To change a *Terraform* setting
(size, budget, `enable_waf`, `git_ref`) edit `terraform.tfvars` and run `terraform apply` again.
A changed `git_ref` does not redeploy the running server: run `update.sh` on it.

## Tear down

```bash
terraform destroy
```

This removes the server, its disk (**including the debate archive**), the public IP, CloudFront, the
secret, the alarms and the budget. **The disk snapshots stay behind** (Terraform does not manage the
snapshots the scheduler creates): delete them under EC2 → Snapshots.

## Things to know

- **The state file contains your secrets.** `terraform.tfstate` is written next to the code and holds
  the keys in plain text (`sensitive` only hides them from screen output). It is git-ignored; keep it
  private. For anything beyond a personal project, store state in an encrypted S3 bucket
  (`backend "s3"`) instead.
- **Firewall (`enable_waf = true`).** Adds a WAF web ACL (1000 requests per 5 minutes per IP, plus AWS's
  common rules), roughly 8 USD a month. Unlike the CloudFormation version it works from any region:
  Terraform creates it in us-east-1 through a second provider.
- **Secret recovery window.** The secret is deleted immediately on `destroy`, so you can re-create the
  stack straight away with the same name.
- **Provider lock file.** `terraform init` creates `.terraform.lock.hcl`; commit it if you keep your own fork.
- **Port 80 is open to the internet** (CloudFront's addresses change), as in the CloudFormation version.
  The admin endpoint still needs its token and opinion requests are capped site-wide.
