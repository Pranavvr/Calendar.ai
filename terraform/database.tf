# RDS Postgres — single db.t4g.micro instance (free tier eligible for 12 months).
# Uses AWS-managed master password stored in Secrets Manager for rotation-friendliness.

resource "aws_db_subnet_group" "cal_ai" {
  name       = "${var.project_name}-db-subnet-group"
  subnet_ids = data.aws_subnets.default.ids
}

resource "aws_db_instance" "cal_ai" {
  identifier                  = "${var.project_name}-db"
  engine                      = "postgres"
  engine_version              = "16"
  instance_class              = "db.t4g.micro"
  allocated_storage           = 20
  storage_type                = "gp3"
  storage_encrypted           = true
  db_name                     = "cal_ai"
  username                    = "cal_ai_admin"
  manage_master_user_password = true # AWS generates + stores in Secrets Manager
  db_subnet_group_name        = aws_db_subnet_group.cal_ai.name
  vpc_security_group_ids      = [aws_security_group.rds.id]
  apply_immediately           = true

  # Not publicly reachable. This was previously true and commented "temporary,
  # for initial migration from laptop" — but it was permanent config, leaving
  # the database exposed to the internet with only a security group in front.
  # Migrations now run from inside the VPC; see deploy.sh.
  publicly_accessible = false

  # --- Durability ---------------------------------------------------------
  # backup_retention_period was never set, so it took the provider default of 0
  # and automated backups were disabled entirely. Combined with
  # skip_final_snapshot, an instance failure or a stray destroy meant total,
  # unrecoverable data loss — including every user's Google authorization.
  #
  # 7 days of automated backups is free: AWS provides backup storage up to the
  # size of the instance's provisioned storage at no charge, and this instance
  # is nowhere near 20GB. Point-in-time recovery comes with it.
  backup_retention_period = 7
  backup_window           = "07:00-08:00" # UTC, ~3am US Eastern
  maintenance_window      = "sun:08:30-sun:09:30"

  # Take a final snapshot on destroy. destroy.sh is run routinely to control
  # cost, and the previous setting made every teardown lossy by default.
  # The timestamp keeps identifiers unique across repeated cycles.
  skip_final_snapshot       = false
  final_snapshot_identifier = "${var.project_name}-final-${formatdate("YYYYMMDDhhmmss", timestamp())}"

  # Left off deliberately: this is a single-AZ instance for a portfolio project
  # and deletion protection would break the routine teardown that keeps the
  # monthly bill near zero. The final snapshot above is the safety net instead.
  deletion_protection = false

  # Minor version patches apply themselves during the maintenance window.
  auto_minor_version_upgrade = true

  lifecycle {
    # final_snapshot_identifier embeds timestamp(), which changes on every plan
    # and would otherwise show a perpetual diff.
    ignore_changes = [final_snapshot_identifier]
  }
}
