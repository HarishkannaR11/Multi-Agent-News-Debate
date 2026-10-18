# Deploy on AWS (using your AWS credits)

> Prefer Terraform to the console? See [`DEPLOY_TERRAFORM.md`](DEPLOY_TERRAFORM.md): the same stack, defined in code. Use one method or the other, not both.

Everything runs on **one EC2 server** that you create from a form in the AWS console. You do not
install anything on your computer.

```
browser ──https──▶ CloudFront ──http──▶ EC2 server ─┬─ Caddy (router, port 80)
                                                    ├─ frontend  (Next.js)
                                                    ├─ backend   (FastAPI + content filters)
                                                    └─ Redis     (debates, opinions)
                                    Secrets Manager ──▶ API keys, read by the server at boot
```

One address serves the website and the API, so there is no CORS setup, and CloudFront provides the
HTTPS certificate. The built-in scheduler generates the debate every day at 07:00 UTC because the
server never sleeps.

## Read this first: it is not free forever

AWS credits are not the same as free. Rough figures (check the
[EC2 pricing page](https://aws.amazon.com/ec2/pricing/on-demand/) and the AWS Free Tier terms; I
could not verify current prices from here):

| Item | Approx. cost |
|---|---|
| `c7i-flex.large` (2 vCPU, 4 GB), the default | ~$60 / month |
| `t3.medium` (2 vCPU, 4 GB; **Paid plan accounts only**) | ~$30 / month |
| Public IP + 30 GB disk + secrets + CloudFront | ~$7 / month |

New accounts get about $100–200 in credits for about 6 months. At the default size that is roughly
**2–3 months** of running 24/7. Ways to stretch it:

- **Stop the server when you don't need it** (EC2 → Instances → *Instance state → Stop*). A stopped
  instance doesn't charge for compute; the disk and IP still cost a few dollars. Start it again
  later; the address and your data stay the same.
- Set the **budget alert** (the template asks for an email and a monthly limit).
- When you are finished, **delete the stack** (see *Tear down*).

On the AWS **Free plan**, the account closes at the end of the trial unless you upgrade to a Paid
plan (AWS gives a grace period), so don't leave anything you care about only here.

## What you need

1. **Know which branch is deployed.** The server downloads the code from GitHub. The finished code
   is on **`main`** (merged in
   [PR #3](https://github.com/HarishkannaR11/Multi-Agent-News-Debate/pull/3)), which is the
   template's default *GitRef*.
2. A **Groq API key** ([console.groq.com](https://console.groq.com)).
3. A **news API key**: [NewsAPI](https://newsapi.org) or [GNews](https://gnews.io).
4. An **admin token**: any long random string. In Windows PowerShell:

   ```powershell
   [guid]::NewGuid().ToString("N") + [guid]::NewGuid().ToString("N")
   ```

   (On Mac/Linux: `openssl rand -hex 32`.)
5. An **email address** for the budget alerts.

Keep the keys in a private note. Don't paste them into chats or the repository.

## Steps

### 1. Pick a region
Top-right of the AWS console. **US East (N. Virginia) `us-east-1`** is the safest choice: the
`c7i-flex` / `m7i-flex` sizes are not offered in every region. Stay in one region for everything.

### 2. Check which sizes your account may use
EC2 → **Launch instance** → look at the instance-type list and note which of `c7i-flex.large`,
`m7i-flex.large`, `t3.medium`, `t3.large` say **Free tier eligible**. (Free plan accounts are
limited; the exact list can differ by region and over time.) You don't actually launch anything,
just close the page. If none of the four is allowed, you'd need to upgrade to a Paid plan first.

### 3. Create the stack
1. Download the template: [`deploy/aws/cloudformation.yaml`](../deploy/aws/cloudformation.yaml)
   (open it on GitHub, click **Raw**, save the page as `cloudformation.yaml`).
2. AWS console → **CloudFormation** → **Create stack** → **With new resources (standard)**.
3. **Upload a template file** → choose the file → **Next**.
4. Stack name: `counterpoint`. Fill in the parameters:

   | Parameter | Value |
   |---|---|
   | GroqApiKey | your Groq key |
   | NewsApiKey / GNewsApiKey | whichever you have (leave the other empty) |
   | AdminToken | the long random string |
   | AlertEmail | your email |
   | MonthlyBudgetUsd | e.g. `40` |
   | InstanceType | one marked *Free tier eligible* in step 2 (default `c7i-flex.large`) |
   | EnableWaf | `false` (default). `true` adds a firewall (about 8 USD/month) and only works in `us-east-1` |
   | GitRef | `main` (leave the default) |
   | Leave the rest as they are | |

5. **Next** → **Next** → tick **"I acknowledge that AWS CloudFormation might create IAM
   resources"** → **Submit**.
6. Wait for the stack status **CREATE_COMPLETE** (about 5 minutes). If it ends in
   *ROLLBACK*, open the **Events** tab: the first red line says why (see *Troubleshooting*).

### 4. Wait for the first boot (10–15 minutes)
CloudFormation finishes before the server does: the server now builds the app. Open the stack's
**Outputs** tab and click **HealthCheck**. Until it shows `{"status":"ready"}` you will see a
CloudFront error page, which is normal while it builds.

### 5. Check the public site (optional, 1 minute)
On your own computer (needs `curl`, `jq`, and `pip install websockets`):

```bash
deploy/aws/check_site.sh https://<the SiteUrl from the Outputs tab>
```

It checks HTTPS, the redirect from http, the API, the protected admin route and, the part I could
not test myself, a **WebSocket through CloudFront**. Opening the site in a browser also proves it:
the page loads its debate over that same WebSocket.

### 6. Generate the first debate
1. EC2 → **Instances** → select `counterpoint` → **Connect** → **Session Manager** → **Connect**.
   (If Session Manager is greyed out, wait a few minutes after boot and refresh.)
2. In the terminal that opens, run:

   ```bash
   sudo /opt/counterpoint/app/deploy/aws/run-daily.sh
   ```

   It prints `Debate saved: <the topic>` when done (a minute or two).
3. Open **SiteUrl** from the stack Outputs. You should see the debate.

From now on a new debate is generated every day at 07:00 UTC.

## Everyday operations (all in Session Manager)

| Task | Command |
|---|---|
| Watch the first-boot progress | `sudo tail -f /var/log/counterpoint-bootstrap.log` |
| Backend logs | `sudo docker compose -f /opt/counterpoint/app/deploy/aws/docker-compose.yml logs -f backend` |
| Generate another debate | `sudo FORCE=true /opt/counterpoint/app/deploy/aws/run-daily.sh` |
| Update to the latest code | `sudo /opt/counterpoint/app/deploy/aws/update.sh` (or from CloudShell: `deploy/aws/redeploy.sh`, see [`DEPLOY_TERRAFORM.md`](DEPLOY_TERRAFORM.md#deploy-a-change-to-the-product)) |
| Change a key | Secrets Manager → open the secret → edit; then run the update command above |
| Rotate the admin token | Secrets Manager → edit `ADMIN_TOKEN` → run the update command above. Also update the `ADMIN_TOKEN` secret in GitHub if you use the *Daily debate* workflow |
| Run the health check by hand | `sudo bash -c '. /etc/counterpoint.env && /opt/counterpoint/app/deploy/aws/healthcheck.sh'` |

## Monitoring, backups and the optional firewall

- **Health alarm.** Every 5 minutes the server runs `healthcheck.sh` and publishes one CloudWatch
  metric, `Counterpoint/Healthy` (1 = fine). The **HealthAlarm** emails `AlertEmail` when it is 0 for
  15 minutes: the backend is not ready (backend or Redis down) or **no new debate has been created for
  36 hours** (the daily job is failing). A second alarm, **ServerStatusAlarm**, fires on AWS's own
  instance status checks. **Confirm the subscription**: AWS sends a "Confirm subscription" email to
  `AlertEmail` right after the stack is created; alarms stay silent until you click it.
- The alarms and metric cost well under 1 USD a month.
- **Stopping the server to save credits** produces no data, which is *not* treated as an alarm.
  Stopping and starting keeps the same public address (Elastic IP), so the site comes back by itself.
- **Backups.** A daily 03:00 UTC snapshot of the server disk is kept for 3 days (Data Lifecycle
  Manager). Debates expire after 30 days anyway, so this mostly protects the Redis data between
  deployments. **Deleting the stack does not delete the snapshots**: remove them under
  EC2 → Snapshots when you tear everything down (they cost a few cents a month).
- **Firewall (optional).** `EnableWaf=true` puts an AWS WAF web ACL in front of CloudFront: 1000
  requests per 5 minutes per IP, plus AWS's common attack rules. It needs `us-east-1`.

## Tear down
CloudFormation → select the stack → **Delete**. This removes the server, the disk (**including the
debate archive**), the public IP, CloudFront, the secret, the alarms and the budget. The disk
snapshots stay behind: delete them under EC2 → Snapshots.

## Troubleshooting

| Symptom | Likely cause |
|---|---|
| Stack rolls back: *"instance type is not eligible"* / *"not supported in this region"* | Choose another `InstanceType` (step 2), or another region such as `us-east-1` |
| Stack rolls back: *"No default VPC"* | Your region has no default network; pick another region |
| HealthCheck shows a CloudFront 502/504 for more than 20 minutes | The build failed; run `sudo tail -n 80 /var/log/counterpoint-bootstrap.log` |
| Site loads but says *"No debate found"* | Run the *Generate the first debate* step |
| `run-daily.sh` says *"no new debate"* | Backend logs (above): usually a wrong/expired Groq or news key |
| `run-daily.sh` says *"admin token rejected"* | The token you put in the stack differs from the one in Secrets Manager |
| Everything is slow or restarts | The server ran out of memory: use a 4 GB+ size (`c7i-flex.large`, `t3.medium`) |

## Security notes

- No SSH: the only open port is 80, and you reach the server through Session Manager.
- The API keys live in Secrets Manager and are read by the server at boot, not stored in the
  instance's user data. The `.env` the server writes is readable only by root.
- Port 80 accepts traffic from anywhere (CloudFront's addresses change). Someone who finds the
  server's raw address could bypass CloudFront; the admin endpoint still needs its token and
  opinion requests are capped site-wide. To lock it down further, restrict the security group to the
  CloudFront origin-facing prefix list.

## Known unknowns

This stack has not been run on a real AWS account (I can't reach one). What *has* been checked:
the template passes `cfn-lint`, the scripts pass `shellcheck`, and CI starts the same
Docker Compose stack and tests routing, WebSockets and rate limiting through the Caddy router.
What has not: CloudFormation actually creating it (including the alarms, snapshot schedule and
optional WAF added later), CloudFront's WebSocket handling in front of the server (`check_site.sh`
tests exactly this once it exists), the exact instance sizes your account allows, and current prices. If the stack fails, the
error text in CloudFormation's **Events** tab or the bootstrap log will say where, and I can fix it
from that.
