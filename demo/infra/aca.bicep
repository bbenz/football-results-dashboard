targetScope = 'resourceGroup'

param location string = resourceGroup().location
param projectTag string
param eventDateTag string
param teardownDateTag string
param acaEnvironmentName string
param logAnalyticsName string
param webAppName string
param insightsAppName string
param ingestJobName string
param acaWebIdentityName string
param acaInsightsIdentityName string
param acaIngestIdentityName string
param registryLoginServer string
param webImageDigest string
param insightsImageDigest string
param ingestImageDigest string
param applicationInsightsConnectionString string
param storageAccountUrl string
param foundryProjectEndpoint string
param aiModelDeployment string = 'gpt-6-astra'
param aiAllowedDeployments string = 'gpt-6-astra,gpt-6-sol'
param webAllowedCidrs array
@description('False deploys only the environment and the ingest job, so the first ingest can run before insights starts.')
param deployApps bool = true

// Per-client page limit sized for the bounded load test (at most 50 requests per second from one address).
// Model-backed questions keep the app's default limit of 6 per minute.
var webPageRateLimitPerMinute = '3600'

var tags = {
  project: projectTag
  'event-date': eventDateTag
  'teardown-date': teardownDateTag
}

resource workspace 'Microsoft.OperationalInsights/workspaces@2025-02-01' existing = {
  name: logAnalyticsName
}

resource webIdentity 'Microsoft.ManagedIdentity/userAssignedIdentities@2024-11-30' existing = { name: acaWebIdentityName }
resource insightsIdentity 'Microsoft.ManagedIdentity/userAssignedIdentities@2024-11-30' existing = { name: acaInsightsIdentityName }
resource ingestIdentity 'Microsoft.ManagedIdentity/userAssignedIdentities@2024-11-30' existing = { name: acaIngestIdentityName }

resource environment 'Microsoft.App/managedEnvironments@2026-01-01' = {
  name: acaEnvironmentName
  location: location
  tags: tags
  properties: {
    appLogsConfiguration: {
      destination: 'log-analytics'
      logAnalyticsConfiguration: {
        customerId: workspace.properties.customerId
      }
    }
    workloadProfiles: [
      {
        name: 'Consumption'
        workloadProfileType: 'Consumption'
      }
    ]
  }
}

var commonEnv = [
  { name: 'PLATFORM_REGION', value: location }
  { name: 'APPLICATIONINSIGHTS_CONNECTION_STRING', value: applicationInsightsConnectionString }
]

// Only insights and ingest read the curated store; web reaches data through insights.
var curatedEnv = [
  { name: 'CURATED_SOURCE', value: 'blob' }
  { name: 'STORAGE_ACCOUNT_URL', value: storageAccountUrl }
  { name: 'CURATED_CONTAINER', value: 'curated' }
]

resource insightsApp 'Microsoft.App/containerApps@2026-01-01' = if (deployApps) {
  name: insightsAppName
  location: location
  tags: tags
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: {
      '${insightsIdentity.id}': {}
    }
  }
  properties: {
    managedEnvironmentId: environment.id
    workloadProfileName: 'Consumption'
    configuration: {
      activeRevisionsMode: 'Single'
      ingress: {
        external: false
        targetPort: 8081
        transport: 'http'
      }
      registries: [
        {
          server: registryLoginServer
          identity: insightsIdentity.id
        }
      ]
    }
    template: {
      scale: {
        minReplicas: 1
        maxReplicas: 5
        rules: [
          {
            name: 'http-concurrency'
            http: {
              metadata: {
                concurrentRequests: '20'
              }
            }
          }
        ]
      }
      containers: [
        {
          name: 'insights'
          image: '${registryLoginServer}/football-insights-insights@${insightsImageDigest}'
          resources: {
            cpu: json('0.5')
            memory: '1Gi'
          }
          env: concat(commonEnv, curatedEnv, [
            { name: 'PLATFORM_NAME', value: 'ACA' }
            { name: 'IMAGE_DIGEST', value: insightsImageDigest }
            { name: 'OTEL_SERVICE_NAME', value: 'insights' }
            { name: 'AZURE_CLIENT_ID', value: insightsIdentity.properties.clientId }
            { name: 'FOUNDRY_PROJECT_ENDPOINT', value: foundryProjectEndpoint }
            { name: 'AI_MODEL_DEPLOYMENT', value: aiModelDeployment }
            { name: 'AI_ALLOWED_DEPLOYMENTS', value: aiAllowedDeployments }
          ])
          probes: [
            { type: 'Liveness', httpGet: { path: '/healthz', port: 8081 }, periodSeconds: 15 }
            { type: 'Readiness', httpGet: { path: '/readyz', port: 8081 }, periodSeconds: 10 }
          ]
        }
      ]
    }
  }
}

resource webApp 'Microsoft.App/containerApps@2026-01-01' = if (deployApps) {
  name: webAppName
  location: location
  tags: tags
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: {
      '${webIdentity.id}': {}
    }
  }
  properties: {
    managedEnvironmentId: environment.id
    workloadProfileName: 'Consumption'
    configuration: {
      activeRevisionsMode: 'Multiple'
      ingress: {
        external: true
        targetPort: 8080
        transport: 'http'
        traffic: [
          { latestRevision: true, weight: 100 }
        ]
        ipSecurityRestrictions: [for (cidr, i) in webAllowedCidrs: {
          name: 'allow-${i}'
          ipAddressRange: cidr
          action: 'Allow'
        }]
      }
      registries: [
        {
          server: registryLoginServer
          identity: webIdentity.id
        }
      ]
    }
    template: {
      scale: {
        minReplicas: 1
        maxReplicas: 5
        rules: [
          {
            name: 'http-concurrency'
            http: {
              metadata: {
                concurrentRequests: '20'
              }
            }
          }
        ]
      }
      containers: [
        {
          name: 'web'
          image: '${registryLoginServer}/football-insights-web@${webImageDigest}'
          resources: {
            cpu: json('0.5')
            memory: '1Gi'
          }
          env: concat(commonEnv, [
            { name: 'PLATFORM_NAME', value: 'ACA' }
            { name: 'IMAGE_DIGEST', value: webImageDigest }
            { name: 'OTEL_SERVICE_NAME', value: 'web' }
            { name: 'AZURE_CLIENT_ID', value: webIdentity.properties.clientId }
            { name: 'INSIGHTS_URL', value: 'http://${insightsAppName}' }
            { name: 'WEB_RATE_LIMIT_PER_MINUTE', value: webPageRateLimitPerMinute }
          ])
          probes: [
            { type: 'Liveness', httpGet: { path: '/healthz', port: 8080 }, periodSeconds: 15 }
            { type: 'Readiness', httpGet: { path: '/readyz', port: 8080 }, periodSeconds: 10 }
          ]
        }
      ]
    }
  }
}

resource ingestJob 'Microsoft.App/jobs@2026-01-01' = {
  name: ingestJobName
  location: location
  tags: tags
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: {
      '${ingestIdentity.id}': {}
    }
  }
  properties: {
    environmentId: environment.id
    workloadProfileName: 'Consumption'
    configuration: {
      triggerType: 'Manual'
      replicaTimeout: 1800
      replicaRetryLimit: 1
      registries: [
        {
          server: registryLoginServer
          identity: ingestIdentity.id
        }
      ]
    }
    template: {
      containers: [
        {
          name: 'ingest'
          image: '${registryLoginServer}/football-insights-ingest@${ingestImageDigest}'
          command: [ 'python', '-m', 'football_insights', 'ingest', '--source', 'blob' ]
          resources: {
            cpu: json('0.5')
            memory: '1Gi'
          }
          env: concat(commonEnv, curatedEnv, [
            { name: 'PLATFORM_NAME', value: 'ACA' }
            { name: 'IMAGE_DIGEST', value: ingestImageDigest }
            { name: 'OTEL_SERVICE_NAME', value: 'ingest' }
            { name: 'AZURE_CLIENT_ID', value: ingestIdentity.properties.clientId }
            { name: 'RAW_CONTAINER', value: 'raw' }
          ])
        }
      ]
    }
  }
}

output webFqdn string = deployApps ? webApp!.properties.configuration.ingress.fqdn : ''
output insightsInternalUrl string = 'http://${insightsAppName}'
output ingestJobName string = ingestJob.name
