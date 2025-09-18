#!/bin/bash

# MCP Azure Entra ID Setup Script
# This script automates the configuration of MCP Client and Server applications in Azure Entra ID

set -e  # Exit on error

# Default application names (can be overridden by environment variables or command line)
CLIENT_APP_NAME="${CLIENT_APP_NAME:-mcp-workshop-client}"
SERVER_APP_NAME="${SERVER_APP_NAME:-mcp-workshop-server}"

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to print colored output
print_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

# Function to show usage information
show_usage() {
    echo "Usage: $0 [OPTIONS]"
    echo ""
    echo "Options:"
    echo "  --client-name NAME    Set the client application name (default: mcp-workshop-client)"
    echo "  --server-name NAME    Set the server application name (default: mcp-workshop-server)"
    echo "  -h, --help           Show this help message"
    echo ""
    echo "Environment Variables:"
    echo "  CLIENT_APP_NAME      Set the client application name"
    echo "  SERVER_APP_NAME      Set the server application name"
    echo ""
    echo "Examples:"
    echo "  $0                                           # Use default names"
    echo "  $0 --client-name my-client --server-name my-server"
    echo "  CLIENT_APP_NAME=my-client $0                 # Using environment variable"
    echo ""
}

# Function to parse command line arguments
parse_arguments() {
    while [[ $# -gt 0 ]]; do
        case $1 in
            --client-name)
                if [[ -n $2 && $2 != --* ]]; then
                    CLIENT_APP_NAME="$2"
                    shift 2
                else
                    print_error "Error: --client-name requires a value"
                    show_usage
                    exit 1
                fi
                ;;
            --server-name)
                if [[ -n $2 && $2 != --* ]]; then
                    SERVER_APP_NAME="$2"
                    shift 2
                else
                    print_error "Error: --server-name requires a value"
                    show_usage
                    exit 1
                fi
                ;;
            -h|--help)
                show_usage
                exit 0
                ;;
            *)
                print_error "Error: Unknown option $1"
                show_usage
                exit 1
                ;;
        esac
    done
}

# Function to check if required tools are installed
check_prerequisites() {
    print_info "Checking prerequisites..."
    
    # Check for Azure CLI
    if ! command -v az &> /dev/null; then
        print_error "Azure CLI is not installed. Please install it from: https://docs.microsoft.com/en-us/cli/azure/install-azure-cli"
        exit 1
    fi
    
    # Check for jq
    if ! command -v jq &> /dev/null; then
        print_error "jq is not installed. Please install it:"
        echo "  - macOS: brew install jq"
        echo "  - Ubuntu/Debian: sudo apt-get install jq"
        echo "  - RHEL/CentOS: sudo yum install jq"
        exit 1
    fi
    
    # Check for uuidgen
    if ! command -v uuidgen &> /dev/null; then
        print_error "uuidgen is not installed. Please install uuid-runtime package."
        exit 1
    fi
    
    print_success "All prerequisites are installed"
}

# Function to check Azure login
check_azure_login() {
    print_info "Checking Azure login status..."
    
    if ! az account show &> /dev/null; then
        print_warning "Not logged into Azure. Please login..."
        az login
    fi
    
    TENANT_ID=$(az account show --query tenantId -o tsv)
    SUBSCRIPTION=$(az account show --query name -o tsv)
    
    print_success "Logged into Azure"
    echo "  Tenant ID: $TENANT_ID"
    echo "  Subscription: $SUBSCRIPTION"
    echo ""
    
    read -p "Is this the correct tenant? (y/n): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        print_info "Please switch to the correct tenant using: az login --tenant <TENANT_ID>"
        exit 1
    fi
}

# Function to create MCP Client Application
create_mcp_client() {
    print_info "Creating $CLIENT_APP_NAME Application..."
    
    # Check if app already exists
    EXISTING_CLIENT=$(az ad app list --display-name "$CLIENT_APP_NAME" --query "[0].appId" -o tsv 2>/dev/null || true)
    
    if [ ! -z "$EXISTING_CLIENT" ]; then
        print_warning "$CLIENT_APP_NAME application already exists with ID: $EXISTING_CLIENT"
        read -p "Do you want to delete and recreate it? (y/n): " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            az ad app delete --id "$EXISTING_CLIENT"
            print_success "Deleted existing $CLIENT_APP_NAME application"
        else
            CLIENT_APP_ID="$EXISTING_CLIENT"
            print_info "Using existing $CLIENT_APP_NAME application"
            return
        fi
    fi
    
    # Create the MCP Client application
    print_info "Registering $CLIENT_APP_NAME application..."
    CLIENT_APP_ID=$(az ad app create \
        --display-name "$CLIENT_APP_NAME" \
        --sign-in-audience "AzureADMyOrg" \
        --enable-access-token-issuance true \
        --enable-id-token-issuance false \
        --requested-access-token-version 2 \
        --is-fallback-public-client true \
        --query appId -o tsv)
    
    print_success "Created $CLIENT_APP_NAME with ID: $CLIENT_APP_ID"
        
    # Create service principal
    print_info "Creating service principal for $CLIENT_APP_NAME..."
    az ad sp create --id "$CLIENT_APP_ID" &> /dev/null || true
    
    print_success "MCP Client Application configured successfully"
}

# Function to create MCP Server Application
create_mcp_server() {
    print_info "Creating $SERVER_APP_NAME Application..."
    
    # Check if app already exists
    EXISTING_SERVER=$(az ad app list --display-name "$SERVER_APP_NAME" --query "[0].appId" -o tsv 2>/dev/null || true)
    
    if [ ! -z "$EXISTING_SERVER" ]; then
        print_warning "$SERVER_APP_NAME application already exists with ID: $EXISTING_SERVER"
        read -p "Do you want to delete and recreate it? (y/n): " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            az ad app delete --id "$EXISTING_SERVER"
            print_success "Deleted existing $SERVER_APP_NAME application"
        else
            SERVER_APP_ID="$EXISTING_SERVER"
            print_info "Using existing $SERVER_APP_NAME application"
            
            # Still need to get or create a new secret
            read -p "Do you want to create a new client secret? (y/n): " -n 1 -r
            echo
            if [[ $REPLY =~ ^[Yy]$ ]]; then
                create_client_secret
            else
                print_warning "Using existing secret (make sure you have it saved)"
                CLIENT_SECRET="<existing-secret-not-retrieved>"
            fi
            return
        fi
    fi
    
    # Create the MCP Server application
    print_info "Registering $SERVER_APP_NAME application..."
    SERVER_APP_ID=$(az ad app create \
        --display-name "$SERVER_APP_NAME" \
        --sign-in-audience "AzureADMyOrg" \
        --enable-access-token-issuance true \
        --enable-id-token-issuance false \
        --requested-access-token-version 2 \
        --query appId -o tsv)
    
    print_success "Created $SERVER_APP_NAME with ID: $SERVER_APP_ID"
    
    # Create client secret
    create_client_secret
        
    # Set Application ID URI
    print_info "Setting Application ID URI..."
    az ad app update --id "$SERVER_APP_ID" --identifier-uris "api://$SERVER_APP_ID"
    
    # Create service principal
    print_info "Creating service principal for $SERVER_APP_NAME..."
    az ad sp create --id "$SERVER_APP_ID" &> /dev/null || true
    
    print_success "MCP Server Application configured successfully"
}

# Function to create client secret
create_client_secret() {
    print_info "Creating client secret..."
        
    SECRET_OUTPUT=$(az ad app credential reset \
        --id "$SERVER_APP_ID" \
        --display-name "$SERVER_APP_NAME-Secret-$(date +%Y%m%d)")
    
    CLIENT_SECRET=$(echo "$SECRET_OUTPUT" | jq -r '.password')
    
    print_success "Client secret created"
    print_warning "IMPORTANT: Save this secret securely - you won't be able to retrieve it later!"
    echo "Client Secret: $CLIENT_SECRET"
    echo ""
    read -p "Press enter when you've saved the secret..."
}

# Function to configure API scopes
configure_api_scopes() {
    print_info "Configuring API scopes..."
    
    # Generate UUIDs for scopes
    SCOPE_ID_PROMPTS=$(uuidgen | tr '[:upper:]' '[:lower:]')
    SCOPE_ID_TOOLS=$(uuidgen | tr '[:upper:]' '[:lower:]')
    SCOPE_ID_RESOURCES=$(uuidgen | tr '[:upper:]' '[:lower:]')
    
    # Create the scopes JSON using jq to ensure proper formatting
    SCOPES_JSON=$(jq -n \
        --arg prompts_id "$SCOPE_ID_PROMPTS" \
        --arg tools_id "$SCOPE_ID_TOOLS" \
        --arg resources_id "$SCOPE_ID_RESOURCES" \
        '{
            oauth2PermissionScopes: [
                {
                    adminConsentDescription: "Allow the app to access MCP Prompts",
                    adminConsentDisplayName: "Access MCP Prompts",
                    id: $prompts_id,
                    isEnabled: true,
                    type: "User",
                    userConsentDescription: "Allow the app to access MCP Prompts on your behalf",
                    userConsentDisplayName: "Access MCP Prompts",
                    value: "MCP.Prompts"
                },
                {
                    adminConsentDescription: "Allow the app to access MCP Tools",
                    adminConsentDisplayName: "Access MCP Tools",
                    id: $tools_id,
                    isEnabled: true,
                    type: "User",
                    userConsentDescription: "Allow the app to access MCP Tools on your behalf",
                    userConsentDisplayName: "Access MCP Tools",
                    value: "MCP.Tools"
                },
                {
                    adminConsentDescription: "Allow the app to access MCP Resources",
                    adminConsentDisplayName: "Access MCP Resources",
                    id: $resources_id,
                    isEnabled: true,
                    type: "User",
                    userConsentDescription: "Allow the app to access MCP Resources on your behalf",
                    userConsentDisplayName: "Access MCP Resources",
                    value: "MCP.Resources"
                }
            ]
        }')
    
    # Write to temporary file
    echo "$SCOPES_JSON" > temp-scopes.json

    # Update the application with scopes
    print_info "Updating application with API scopes..."
    if az ad app update --id "$SERVER_APP_ID" --set api=@temp-scopes.json; then
        print_success "API scopes configured:"
        echo "  - api://$SERVER_APP_ID/MCP.Prompts"
        echo "  - api://$SERVER_APP_ID/MCP.Tools"
        echo "  - api://$SERVER_APP_ID/MCP.Resources"
    else
        print_error "Failed to configure API scopes"
        print_info "Manual configuration may be required through Azure Portal"
    fi
    
    # Clean up temp file
    rm -f temp-scopes.json
}

# Function to authorize client applications
authorize_clients() {
    print_info "Authorizing client applications..."
    
    # Get the scope IDs we just created
    SCOPES_JSON=$(az ad app show --id "$SERVER_APP_ID" --query "api.oauth2PermissionScopes" -o json 2>/dev/null || echo "[]")
    
    if [ "$SCOPES_JSON" = "[]" ] || [ -z "$SCOPES_JSON" ]; then
        print_warning "No scopes found. Skipping client authorization."
        return
    fi
    
    # Create pre-authorized applications configuration using jq
    PREAUTH_JSON=$(echo "$SCOPES_JSON" | jq -r \
        --arg client_id "$CLIENT_APP_ID" \
        '{
            preAuthorizedApplications: [
                {
                    appId: $client_id,
                    delegatedPermissionIds: [.[].id]
                },
                {
                    appId: "aebc6443-996d-45c2-90f0-388ff96faa56",
                    delegatedPermissionIds: [.[].id]
                }
            ]
        }')
    
    # Write to temporary file
    echo "$PREAUTH_JSON" > temp-preauth.json
    
    # Update the application
    print_info "Updating pre-authorized applications..."
    if az ad app update --id "$SERVER_APP_ID" --set api=@temp-preauth.json; then
        print_success "Authorized client applications:"
        echo "  - $CLIENT_APP_NAME ($CLIENT_APP_ID)"
        echo "  - Visual Studio Code (aebc6443-996d-45c2-90f0-388ff96faa56)"
    else
        print_warning "Failed to authorize client applications"
        print_info "Manual authorization may be required through Azure Portal"
    fi
    
    # Clean up temp file
    rm -f temp-preauth.json
}

# Function to configure Microsoft Graph permissions
configure_graph_permissions() {
    print_info "Configuring Microsoft Graph permissions..."
    
    # Add Microsoft Graph User.Read permission
    az ad app permission add \
        --id "$SERVER_APP_ID" \
        --api 00000003-0000-0000-c000-000000000000 \
        --api-permissions e1fe6dd8-ba31-4d61-89e7-88639da4683d=Scope \
        2>/dev/null || true
    
    print_success "Added Microsoft Graph User.Read permission"
    
    # Check if user has admin privileges for consent
    read -p "Do you have admin privileges to grant consent? (y/n): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        print_info "Granting admin consent..."
        if az ad app permission admin-consent --id "$SERVER_APP_ID" 2>/dev/null; then
            print_success "Admin consent granted"
        else
            print_warning "Failed to grant admin consent. Please ask an admin to grant consent through the Azure Portal"
        fi
    else
        print_warning "Admin consent required. Please ask an admin to grant consent through the Azure Portal"
    fi
}

# Function to create configuration files
create_config_files() {
    print_info "Creating configuration files..."
    
    # Create servers directory if it doesn't exist
    if [ ! -d "servers" ]; then
        mkdir -p servers
        print_info "Created servers directory"
    fi
    
    # Create clients directory if it doesn't exist
    if [ ! -d "clients" ]; then
        mkdir -p clients
        print_info "Created clients directory"
    fi
    
    # Create server .env file
    cat > servers/.env << EOF
# OAuth Configuration (for weather server demo)
# Generated on $(date)
TENANT_ID=$TENANT_ID
CLIENT_ID=$SERVER_APP_ID
CLIENT_SECRET=$CLIENT_SECRET
SCOPES=MCP.Tools,MCP.Resources,MCP.Prompts
EOF
    
    print_success "Created servers/.env"
    
    # Create client .env file
    cat > clients/.env << EOF
# Azure OpenAI Configuration (required for console client)
# TODO: Update these values with your Azure OpenAI resource details
AZURE_OPENAI_ENDPOINT=https://your-resource.openai.azure.com/
AZURE_OPENAI_API_KEY=your-api-key
AZURE_OPENAI_API_VERSION=2024-02-15-preview
AZURE_OPENAI_DEPLOYMENT=your-deployment-name

# MCP Client Configuration
# Generated on $(date)
CLIENT_ID=$CLIENT_APP_ID
EOF
    
    print_success "Created clients/.env"
    
    # Create a summary file
    cat > mcp-azure-config-summary.txt << EOF
MCP Azure Configuration Summary
Generated on: $(date)
================================

TENANT INFORMATION:
  Tenant ID: $TENANT_ID

MCP CLIENT APPLICATION:
  Application ID: $CLIENT_APP_ID
  Display Name: $CLIENT_APP_NAME

MCP SERVER APPLICATION:
  Application ID: $SERVER_APP_ID
  Display Name: $SERVER_APP_NAME
  Client Secret: [Stored in servers/.env]
  
API SCOPES:
  - api://$SERVER_APP_ID/MCP.Prompts
  - api://$SERVER_APP_ID/MCP.Tools
  - api://$SERVER_APP_ID/MCP.Resources

PRE-AUTHORIZED APPLICATIONS:
  - $CLIENT_APP_NAME: $CLIENT_APP_ID
  - Visual Studio Code: aebc6443-996d-45c2-90f0-388ff96faa56

CONFIGURATION FILES:
  - servers/.env - Contains server OAuth configuration
  - clients/.env - Contains client configuration (update Azure OpenAI settings)

NEXT STEPS:
1. Update the Azure OpenAI settings in clients/.env with your actual values
2. If admin consent was not granted, ask an admin to grant consent in Azure Portal
3. Test the configuration with your MCP client and server applications

TO DELETE THESE APPLICATIONS:
  az ad app delete --id $CLIENT_APP_ID
  az ad app delete --id $SERVER_APP_ID
EOF
    
    print_success "Created configuration summary: mcp-azure-config-summary.txt"
}

# Function to display summary
display_summary() {
    echo ""
    echo "========================================="
    echo "   MCP Azure Configuration Complete!"
    echo "========================================="
    echo ""
    cat mcp-azure-config-summary.txt
    echo ""
    print_warning "IMPORTANT REMINDERS:"
    echo "  1. Update Azure OpenAI settings in clients/.env"
    echo "  2. Keep your client secret secure"
    echo "  3. Grant admin consent if not already done"
    echo ""
}

# Function to cleanup on error
cleanup_on_error() {
    print_error "An error occurred during setup"
    read -p "Do you want to cleanup created resources? (y/n): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        if [ ! -z "$CLIENT_APP_ID" ]; then
            az ad app delete --id "$CLIENT_APP_ID" 2>/dev/null || true
            print_info "Deleted $CLIENT_APP_NAME application"
        fi
        if [ ! -z "$SERVER_APP_ID" ]; then
            az ad app delete --id "$SERVER_APP_ID" 2>/dev/null || true
            print_info "Deleted $SERVER_APP_NAME application"
        fi
        rm -f servers/.env clients/.env mcp-azure-config-summary.txt temp-*.json
        print_info "Cleanup completed"
    fi
    exit 1
}

# Main execution
main() {
    # Parse command line arguments first
    parse_arguments "$@"
    
    clear
    echo "========================================="
    echo "   MCP Azure Entra ID Setup Script"
    echo "========================================="
    echo ""
    print_info "Configuration:"
    echo "  Client App Name: $CLIENT_APP_NAME"
    echo "  Server App Name: $SERVER_APP_NAME"
    echo ""
    
    # Set trap for cleanup on error
    trap cleanup_on_error ERR
    
    # Run setup steps
    check_prerequisites
    check_azure_login
    create_mcp_client
    create_mcp_server
    configure_api_scopes
    authorize_clients
    configure_graph_permissions
    create_config_files
    display_summary
    
    print_success "Setup completed successfully!"
}

# Run main function with all arguments
main "$@"