# RDS Postgres — single db.t4g.micro instance (free tier eligible for 12 months).
# Uses AWS-managed master password stored in Secrets Manager for rotation-friendliness.

resource "aws_db_subnet_group" "cal_ai" {
  name       = "${var.project_name}-db-subnet-group"
  subnet_ids = data.aws_subnets.default.ids
}

resource "aws_db_instance" "cal_ai" {
  identifier             = "${var.project_name}-db"
  engine                 = "postgres"
  engine_version         = "16"
  instance_class         = "db.t4g.micro"
  allocated_storage      = 20
  storage_type           = "gp3"
  storage_encrypted      = true
  db_name                = "cal_ai"
  username               = "cal_ai_admin"
  manage_master_user_password = true # AWS generates + stores in Secrets Manager
  db_subnet_group_name   = aws_db_subnet_group.cal_ai.name
  vpc_security_group_ids = [aws_security_group.rds.id]
  publicly_accessible    = true # temporary, for initial migration from laptop
  skip_final_snapshot    = true # portfolio project; not backing up on destroy
  apply_immediately      = true
  deletion_protection    = false # allow terraform destroy for teardown
}
