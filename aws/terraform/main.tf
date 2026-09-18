terraform {
  required_version = ">= 1.5.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 5.80"
    }
  }
}

provider "aws" {
  region = var.region
}

data "aws_ami" "ubuntu" {
  most_recent = true
  owners      = ["099720109477"]
  filter {
    name   = "name"
    values = ["ubuntu/images/hvm-ssd-gp3/ubuntu-noble-24.04-amd64-server-*"]
  }
  filter {
    name   = "architecture"
    values = ["x86_64"]
  }
}

resource "aws_placement_group" "cluster" {
  name     = "${var.name}-cluster"
  strategy = "cluster"
}

resource "aws_security_group" "efa" {
  name        = "${var.name}-efa"
  description = "EFA self-allow + SSH + harness HTTP. Self-referencing all-traffic is mandatory for EFA."
  vpc_id      = var.vpc_id

  ingress {
    description = "SSH"
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = [var.allowed_ssh_cidr]
  }

  ingress {
    description = "harness rendezvous/files/iperf/nixl"
    from_port   = 5201
    to_port     = 8776
    protocol    = "tcp"
    self        = true
  }

  ingress {
    description = "EFA: all traffic from this SG"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    self        = true
  }

  egress {
    description = "EFA: all traffic to this SG"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    self        = true
  }

  egress {
    description = "internet for packages (install-deps)"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_network_interface" "node" {
  count           = var.node_count
  subnet_id       = var.subnet_id
  security_groups = [aws_security_group.efa.id]
  # "efa" = EFA with ENA so TCP iperf3 and SSH work on the same NIC.
  interface_type = "efa"
  description    = "${var.name}-node${count.index}"
  tags = {
    Name = "${var.name}-node${count.index}"
  }
}

locals {
  ami_id = var.ami_id != "" ? var.ami_id : data.aws_ami.ubuntu.id
}

resource "aws_instance" "node" {
  count                = var.node_count
  ami                  = local.ami_id
  instance_type        = var.instance_type
  key_name             = var.key_name
  iam_instance_profile = var.instance_profile
  placement_group      = aws_placement_group.cluster.id

  network_interface {
    device_index         = 0
    network_interface_id = aws_network_interface.node[count.index].id
  }

  root_block_device {
    volume_size = var.root_volume_gb
    volume_type = "gp3"
  }

  metadata_options {
    http_tokens = "required"
  }

  user_data = templatefile("${path.module}/user-data.sh.tftpl", {
    repo_url = var.repo_url
  })

  tags = {
    Name = "${var.name}-node${count.index}"
    Role = count.index == 0 ? "hub" : "worker"
  }
}

resource "aws_eip" "hub" {
  count  = var.associate_hub_eip ? 1 : 0
  domain = "vpc"
  tags   = { Name = "${var.name}-hub" }
}

resource "aws_eip_association" "hub" {
  count                = var.associate_hub_eip ? 1 : 0
  allocation_id        = aws_eip.hub[0].id
  network_interface_id = aws_network_interface.node[0].id
}
