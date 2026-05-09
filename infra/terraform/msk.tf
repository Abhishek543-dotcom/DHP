# MSK Serverless: simpler ops, IAM auth out of the box, billed per use.
# Switch to provisioned MSK for higher throughput / cheaper steady-state at scale.

resource "aws_msk_serverless_cluster" "main" {
  cluster_name = "${local.name}-msk"

  vpc_config {
    subnet_ids         = aws_subnet.private[*].id
    security_group_ids = [aws_security_group.data.id]
  }

  client_authentication {
    sasl {
      iam {
        enabled = true
      }
    }
  }
}
