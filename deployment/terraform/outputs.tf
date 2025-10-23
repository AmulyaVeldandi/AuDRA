output "cluster_name" {
  description = "Name of the EKS cluster"
  value       = aws_eks_cluster.audra.name
}
