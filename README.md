# Sales AI Assistant
A sample AI Assistant that implements Open AI Assistants API v2 features like File search, Code interpeter.
It implements a Bot Application that helps:
- Sales team to reason with document content and have their questions answered. For e.g. ' What are the benefits of being a Premium Customer?'
- Sales Team can perform analysis on Contoso Product Sales data and Products data using the Code Interpreter.
- It is built using the Microsoft Bot Framework

## Key configuration

1) Azure Bot Resource is created with 'MultiTenant' option selected.
2) The connection strings and secrets used in config.py are available in AKV [here](https://ms.portal.azure.com/#@fdpo.onmicrosoft.com/asset/Microsoft_Azure_KeyVault/Secret/https://demo-env-config-vault.vault.azure.net/secrets/Sales-Ai-Assist-bot-config/a0ed5a1fa4594aa2b862a8cefc2c3abe)

## Steps performed to deploy the Bot Application

On the folder that contains the project code, creat a zip file e.g. sales-assist.zip

Run the following using az cli on VS Code

```cli
az webapp deployment source config-zip --resource-group "sales-assist-rg" --name "sales-assist-web" --src 'sales-assist.zip'

```

Configure the following on the Azure Web App used to host the Bot application

- Start up command. Here the timeout is set to a large value to ensure the request does not time out before the Code interpreter returns the response

```sh
gunicorn --bind 0.0.0.0 --timeout 1000 --worker-class aiohttp.worker.GunicornWebWorker app:APP
```
- In the App Settings, add the following variable
SCM_DO_BUILD_DURING_DEPLOYMENT  & set the value to true