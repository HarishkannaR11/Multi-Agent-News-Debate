#!/usr/bin/env bash
# Redeploy from your own computer or AWS CloudShell: tells the server to pull the newest code from GitHub,
# rebuild and restart, then waits and prints the result. Needs the AWS CLI with access to your account.
#
#   deploy/aws/redeploy.sh                      # deploy the latest main
#   GIT_REF=my-branch deploy/aws/redeploy.sh    # deploy another branch or tag
#
# It reads the instance id from Terraform (deploy/terraform) and the region from terraform.tfvars; override with
#   INSTANCE_ID=i-0123...  AWS_REGION=ap-southeast-2  deploy/aws/redeploy.sh
# Only changes that are already on GitHub are deployed: merge your change into the branch first.

# Stop on the first error, on unset variables, and on failures inside pipelines.
set -euo pipefail

# The folder with the Terraform files (next to this script's folder).
tf_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/../terraform" && pwd)"
# Which branch or tag the server should run (default: main).
ref="${GIT_REF:-main}"
# The server: from the environment, or from Terraform's outputs.
instance_id="${INSTANCE_ID:-$(terraform -chdir="$tf_dir" output -raw instance_id 2>/dev/null || true)}"
# The region: from the environment, or from the aws_region line of terraform.tfvars.
region="${AWS_REGION:-$(awk -F'"' '/^aws_region/ {print $2}' "$tf_dir/terraform.tfvars" 2>/dev/null || true)}"

# Prints "FAIL: <message>" to the error stream and stops the script with an error code.
fail() { echo "FAIL: $*" >&2; exit 1; }

[ -n "$instance_id" ] || fail "could not find the instance id; run from a folder where 'terraform output' works, or set INSTANCE_ID=i-..."
[ -n "$region" ] || fail "could not find the region; set AWS_REGION=ap-southeast-2 (or your region)"
# The ref ends up inside a shell command on the server, so allow only ordinary branch and tag characters.
[[ "$ref" =~ ^[A-Za-z0-9._/-]+$ ]] || fail "GIT_REF may only contain letters, digits, . _ / and -"

app="/opt/counterpoint/app"
# The commands the server runs, as a JSON file for AWS Systems Manager:
#  1-3: make the server's checkout follow the chosen branch (a no-op when it already does)
#  4:   update.sh pulls the newest code, refreshes the secrets and rebuilds and restarts the containers
params="$(mktemp)"
trap 'rm -f "$params"' EXIT
cat > "$params" <<JSON
{"commands": [
  "git -C $app remote set-branches --add origin $ref",
  "git -C $app fetch --depth 1 origin $ref",
  "git -C $app checkout -q -B $ref origin/$ref",
  "$app/deploy/aws/update.sh"
]}
JSON

echo "Deploying '$ref' to $instance_id in $region (this takes a few minutes)..."
# Send the commands to the server. Systems Manager runs them as root there.
command_id="$(aws ssm send-command --region "$region" --instance-ids "$instance_id" \
  --document-name AWS-RunShellScript --parameters "file://$params" \
  --query Command.CommandId --output text)" || fail "could not send the command (is the server registered with Session Manager yet?)"

# Wait for it to finish, checking every 15 seconds for up to 30 minutes.
status="Pending"
for _ in $(seq 1 120); do
  sleep "${POLL_SECONDS:-15}"
  status="$(aws ssm get-command-invocation --region "$region" --command-id "$command_id" \
    --instance-id "$instance_id" --query Status --output text 2>/dev/null || echo Pending)"
  case "$status" in
    Pending | InProgress | Delayed) printf '.' ;;
    *) break ;;
  esac
done
echo

# Show what the server printed (the end of it), and fail if it did not succeed.
aws ssm get-command-invocation --region "$region" --command-id "$command_id" --instance-id "$instance_id" \
  --query '[StandardOutputContent,StandardErrorContent]' --output text | tail -n 25
[ "$status" = "Success" ] || fail "the deployment finished with status: $status"
echo "Done. Check the site, then run deploy/aws/check_site.sh <your site address> if you like."
