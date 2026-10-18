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
`git_ref` is only used when the server is first created. Changing it later does nothing to the running
server (Terraform ignores it on purpose, so it never restarts the server); to deploy newer code run
`update.sh` on the server (see [`DEPLOY_AWS.md`](DEPLOY_AWS.md#everyday-operations-all-in-session-manager)).

## Deploy a change to the product

Changing the app does **not** need Terraform. The server runs whatever is on GitHub, so a code change goes:

1. **Change the code and merge it into `main`** on GitHub (pull request → *Merge*). CI runs the tests and builds
   the images on every pull request; wait for it to be green. Anything not on GitHub is not deployed.
2. **Tell the server to update.** In CloudShell:

   ```bash
   cd ~/Multi-Agent-News-Debate && git pull          # get the latest scripts
   deploy/aws/redeploy.sh
   ```

   It makes the server follow `main`, pulls the new code, rebuilds only what changed and restarts the
   containers, then waits and prints the result (a few minutes; the site may blink for under a minute while
   the changed containers restart). It reads the server's id and region from `deploy/terraform`
   (`INSTANCE_ID=... AWS_REGION=...` override them; `GIT_REF=some-branch` deploys another branch).
   The same thing by hand: Session Manager on the server → `sudo /opt/counterpoint/app/deploy/aws/update.sh`.
3. **Check it:** open the site, and optionally run `deploy/aws/check_site.sh https://<your site>`.

Which tool for which change:

| You changed | Do this |
|---|---|
| App code (backend, frontend, prompts) | Merge to `main`, then `deploy/aws/redeploy.sh` |
| An API key, the admin token or other secret | AWS console → Secrets Manager → `counterpoint-app-secrets` → edit, then `deploy/aws/redeploy.sh` (it rewrites the server's settings) |
| Server size, budget, firewall, domain | Edit `terraform.tfvars`, `terraform plan`, `terraform apply` |
| Only the docs | Nothing to deploy |

A bad deployment can be undone by deploying the previous good commit: `GIT_REF=<old tag or branch> deploy/aws/redeploy.sh`.
The debates already saved are kept in Redis (a Docker volume) and survive a redeploy; they are lost only if the
server is destroyed.

## Use your own domain (for example krisharish.space)

By default the site is on a CloudFront address like `https://d1234abcd.cloudfront.net`. To serve it on your
own domain, AWS needs to give you an HTTPS certificate for it, and the domain's DNS has to point at CloudFront.
Do it in **two applies**, because the certificate must be validated before CloudFront can use it. It works the
same whether the stack already exists or you are creating it now.

First decide **where the domain's DNS is managed**. DNS is the address book of the internet; it is set where you
bought the domain (your *registrar*) unless you move it.

### Option A (recommended): let AWS Route 53 host the DNS

Costs about 0.50 USD a month. Works for the bare domain (`krisharish.space`) and for `www`. Terraform creates
every record for you.

1. In `terraform.tfvars` set:

   ```hcl
   domain_name        = "krisharish.space"
   extra_domain_names = ["www.krisharish.space"]   # optional: also answer on www
   dns_provider       = "route53"
   attach_domain      = false
   ```

2. `terraform apply`. This creates the certificate, a DNS zone and the validation records (a few minutes).
3. `terraform output route53_nameservers` prints four names like `ns-123.awsdns-45.org`. **At the place you
   bought the domain**, switch the domain's *nameservers* to **custom nameservers** and enter those four
   (usually under Domain → Nameservers; remove the old ones). Save.
4. Wait for it to spread, usually 5–60 minutes, rarely a few hours. Check the certificate: AWS console →
   **Certificate Manager**, with the region set to **N. Virginia (us-east-1)** → your certificate must say
   **Issued**. (CloudFront certificates always live in us-east-1.)
5. In `terraform.tfvars` change `attach_domain = true`, then `terraform apply`. CloudFront takes 5–15 minutes
   to update. If the certificate is not issued yet, this apply waits for it; you can stop it with Ctrl+C and
   repeat the step later.
6. Open `https://krisharish.space`. From your computer run `deploy/aws/check_site.sh https://krisharish.space`.

### Option B: keep the DNS at your registrar

No AWS DNS fee, but you add the records by hand, and **many registrars cannot point the bare domain
(`krisharish.space`) at another name**. Use a subdomain such as `www.krisharish.space` or
`debate.krisharish.space`, then forward the bare domain to it with your registrar's "URL redirect" feature (or use
an ALIAS/ANAME record if your registrar offers one).

1. In `terraform.tfvars` set:

   ```hcl
   domain_name   = "www.krisharish.space"
   dns_provider  = "registrar"
   attach_domain = false
   ```

2. `terraform apply`, then `terraform output dns_records_to_create_at_registrar`. It shows a record of type
   `CNAME` with a long `name` and `value`. Create exactly that record in your registrar's DNS settings. Many
   registrars want the name **without** your domain at the end (enter `_abc123.www`, not
   `_abc123.www.krisharish.space.`), and without the trailing dot. **Keep this record forever**: AWS uses it to renew
   the certificate.
3. Wait until **Certificate Manager** (region us-east-1) shows **Issued** (usually minutes).
4. Set `attach_domain = true` and `terraform apply` (5–15 minutes for CloudFront).
5. `terraform output cloudfront_address` prints the CloudFront name. At your registrar create a **CNAME**:
   host `www` (or `debate`) → that CloudFront name.
6. Open `https://www.krisharish.space`.

### Things to know about domains

- The certificate and the Route 53 zone cost nothing extra apart from the 0.50 USD zone fee.
- If you `terraform destroy` and later create the stack again with Option A, the new DNS zone gets **new
  nameservers**: update them at your registrar again.
- The website does not need any change: it already talks to the same address it was loaded from.
- The CloudFormation template (`DEPLOY_AWS.md`) does not have this feature; use Terraform for a custom domain.
- I could not test this against a real domain or AWS account. If a step hangs or errors, send me the
  error text and which step you were on.

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
