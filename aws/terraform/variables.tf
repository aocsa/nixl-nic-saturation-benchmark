variable "region" {
  type    = string
  default = "us-east-1"
}

variable "name" {
  type    = string
  default = "nixl-sat"
}

variable "vpc_id" {
  type = string
}

variable "subnet_id" {
  type        = string
  description = "Private or public subnet in a single AZ. Cluster placement group requires one AZ."
}

variable "key_name" {
  type = string
}

variable "node_count" {
  type        = number
  default     = 3
  description = "N instances. Need >=2 for pairwise; >=3 for m2o/o2m."
}

variable "instance_type" {
  type    = string
  default = "g7e.8xlarge"
}

variable "ami_id" {
  type        = string
  default     = ""
  description = "Empty = Ubuntu 24.04. Prefer a DLAMI that already has NVIDIA + EFA."
}

variable "allowed_ssh_cidr" {
  type    = string
  default = "0.0.0.0/0"
}

variable "root_volume_gb" {
  type    = number
  default = 80
}

variable "instance_profile" {
  type    = string
  default = null
}

variable "associate_hub_eip" {
  type    = bool
  default = true
}

variable "repo_url" {
  type    = string
  default = "https://github.com/aocsa/nixl-nic-saturation-benchmark.git"
}
