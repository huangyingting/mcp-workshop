@description('The location used for all deployed resources')
param location string = resourceGroup().location

@description('Tags that will be applied to all resources')
param tags object = {}


param newsmcpHttpPythonExists bool

@description('Id of the user or app to assign application roles')
param principalId string

@secure()
@description('NewsAPI API key used by the container app')
param newsApiKey string

var abbrs = loadJsonContent('./abbreviations.json')
var resourceToken = uniqueString(subscription().id, resourceGroup().id, location)

// Monitor application with Azure Monitor
module monitoring 'br/public:avm/ptn/azd/monitoring:0.1.0' = {
  name: 'monitoring'
  params: {
    logAnalyticsName: '${abbrs.operationalInsightsWorkspaces}${resourceToken}'
    applicationInsightsName: '${abbrs.insightsComponents}${resourceToken}'
    applicationInsightsDashboardName: '${abbrs.portalDashboards}${resourceToken}'
    location: location
    tags: tags
  }
}
// Container registry
module containerRegistry 'br/public:avm/res/container-registry/registry:0.1.1' = {
  name: 'registry'
  params: {
    name: '${abbrs.containerRegistryRegistries}${resourceToken}'
    location: location
    tags: tags
    publicNetworkAccess: 'Enabled'
    roleAssignments:[
      {
        principalId: newsmcpHttpPythonIdentity.outputs.principalId
        principalType: 'ServicePrincipal'
        roleDefinitionIdOrName: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '7f951dda-4ed3-4680-a7ca-43fe172d538d')
      }
    ]
  }
}

// Container apps environment
module containerAppsEnvironment 'br/public:avm/res/app/managed-environment:0.4.5' = {
  name: 'container-apps-environment'
  params: {
    logAnalyticsWorkspaceResourceId: monitoring.outputs.logAnalyticsWorkspaceResourceId
    name: '${abbrs.appManagedEnvironments}${resourceToken}'
    location: location
    zoneRedundant: false
  }
}

module newsmcpHttpPythonIdentity 'br/public:avm/res/managed-identity/user-assigned-identity:0.2.1' = {
  name: 'newsmcpHttpPythonidentity'
  params: {
    name: '${abbrs.managedIdentityUserAssignedIdentities}newsmcpHttpPython-${resourceToken}'
    location: location
  }
}
module newsmcpHttpPythonFetchLatestImage './modules/fetch-container-image.bicep' = {
  name: 'newsmcpHttpPython-fetch-image'
  params: {
    exists: newsmcpHttpPythonExists
    name: 'newsmcp-http-python'
  }
}

module newsmcpHttpPython 'br/public:avm/res/app/container-app:0.8.0' = {
  name: 'newsmcpHttpPython'
  params: {
    name: 'newsmcp-http-python'
    ingressTargetPort: 8000
    scaleMinReplicas: 1
    scaleMaxReplicas: 10
    secrets: {
      secureList:  [
        {
          name: 'news-api-key'
          value: newsApiKey
        }
      ]
    }
    containers: [
      {
        image: newsmcpHttpPythonFetchLatestImage.outputs.?containers[?0].?image ?? 'mcr.microsoft.com/azuredocs/containerapps-helloworld:latest'
        name: 'main'
        resources: {
          cpu: json('0.5')
          memory: '1.0Gi'
        }
        env: [
          {
            name: 'APPLICATIONINSIGHTS_CONNECTION_STRING'
            value: monitoring.outputs.applicationInsightsConnectionString
          }
          {
            name: 'AZURE_CLIENT_ID'
            value: newsmcpHttpPythonIdentity.outputs.clientId
          }
          {
            name: 'PORT'
            value: '8000'
          }
          {
            name: 'NEWS_API_KEY'
            secretRef: 'news-api-key'
          }          
        ]
      }
    ]
    managedIdentities:{
      systemAssigned: false
      userAssignedResourceIds: [newsmcpHttpPythonIdentity.outputs.resourceId]
    }
    registries:[
      {
        server: containerRegistry.outputs.loginServer
        identity: newsmcpHttpPythonIdentity.outputs.resourceId
      }
    ]
    environmentResourceId: containerAppsEnvironment.outputs.resourceId
    location: location
    tags: union(tags, { 'azd-service-name': 'newsmcp-http-python' })
  }
}
output AZURE_CONTAINER_REGISTRY_ENDPOINT string = containerRegistry.outputs.loginServer
output AZURE_RESOURCE_NEWSMCP_HTTP_PYTHON_ID string = newsmcpHttpPython.outputs.resourceId
