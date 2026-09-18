output "private_ips" {
  value = [for nic in aws_network_interface.node : nic.private_ip]
}

output "node_names" {
  value = [for i in range(var.node_count) : "node${i}"]
}

output "hub_private_ip" {
  value = aws_network_interface.node[0].private_ip
}

output "hub_public_ip" {
  value       = var.associate_hub_eip ? aws_eip.hub[0].public_ip : null
  description = "SSH jump from laptop; workers use private IPs."
}

output "instance_ids" {
  value = [for i in aws_instance.node : i.id]
}

output "ssh_hub" {
  value = var.associate_hub_eip ? "ssh -i KEY ubuntu@${aws_eip.hub[0].public_ip}" : "ssh via SSM / bastion to ${aws_network_interface.node[0].private_ip}"
}

output "inventory_hint" {
  value = join(",", [for i, nic in aws_network_interface.node : "node${i}:${nic.private_ip}:${5550 + i}"])
}
