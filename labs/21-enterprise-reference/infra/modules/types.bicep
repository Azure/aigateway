// Shared user-defined types for the enterprise reference templates.

@export()
@description('A Microsoft Entra principal that gets an AI Gateway data-plane role.')
type principal = {
  @description('Object ID of the user, group, service principal, or managed identity.')
  principalId: string

  @description('Kind of principal.')
  principalType: ('User' | 'Group' | 'ServicePrincipal')
}
