# Terraform core + provider version pins.
#
# required_version >= 1.7.1 is taken verbatim from the local precedent at
# /Users/sac/praxis/deploy/azure/ma-case-study/providers.tf, which documents
# it in-line as the minimum core version where `mock_provider "azurerm" {}`
# and a root `provider "azurerm" { features {} }` block can coexist
# (hashicorp/terraform#34489). This configuration's whole test strategy is
# mocked-provider `terraform test`, so that fix is load-bearing here too.
#
# azurerm ~> 3.90 matches the same precedent. NOTE: the praxis precedent
# splits `terraform {}` into providers.tf and has no versions.tf; this
# configuration splits them because the calling scope asked for both files.
# No `backend` block is declared, deliberately: no backend "azurerm" is
# uncommented anywhere under ~ and this configuration must never acquire
# remote state that could be applied against a real subscription.

terraform {
  required_version = ">= 1.7.1"

  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 3.90"
    }
  }
}
