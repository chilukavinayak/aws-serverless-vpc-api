output "api_endpoint" {
  value = "https://${aws_api_gateway_rest_api.this.id}.execute-api.${var.aws_region}.amazonaws.com/${aws_api_gateway_stage.this.stage_name}"
}

output "rest_api_id" {
  value = aws_api_gateway_rest_api.this.id
}

output "function_names" {
  value = {
    create_vpc = module.create_vpc.function_name
    get_vpc    = module.get_vpc.function_name
    list_vpcs  = module.list_vpcs.function_name
    delete_vpc = module.delete_vpc.function_name
  }
}
