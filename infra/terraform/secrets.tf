resource "random_password" "api_key" {
  length  = 48
  special = false
}

resource "random_password" "internal_token" {
  length  = 48
  special = false
}

resource "aws_secretsmanager_secret" "app" {
  name                    = "${local.name}/app"
  description             = "DHP application secrets"
  recovery_window_in_days = var.environment == "prod" ? 7 : 0
}

resource "aws_secretsmanager_secret_version" "app" {
  secret_id = aws_secretsmanager_secret.app.id
  secret_string = jsonencode({
    API_KEY            = random_password.api_key.result
    INTERNAL_API_TOKEN = random_password.internal_token.result
    DATABASE_URL = format(
      "postgresql+asyncpg://%s:%s@%s:5432/%s",
      var.db_username,
      random_password.db.result,
      aws_db_instance.main.address,
      var.db_name,
    )
    DATABASE_PASSWORD = random_password.db.result
  })
}
