# SNS topic for CloudWatch alarm notifications. Email addresses listed in
# var.alarm_emails are subscribed automatically; each recipient must confirm
# the AWS subscription email before alerts will be delivered.

resource "aws_sns_topic" "alerts" {
  name = "${local.name}-alerts"
}

resource "aws_sns_topic_subscription" "alerts_email" {
  for_each  = toset(var.alarm_emails)
  topic_arn = aws_sns_topic.alerts.arn
  protocol  = "email"
  endpoint  = each.value
}
