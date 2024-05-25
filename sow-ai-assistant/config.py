#!/usr/bin/env python3
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.
import os
import openai
class DefaultConfig:
    """ Bot Configuration """
    PORT = 3978
    APP_ID = os.environ.get("MicrosoftAppId", "")
    APP_PASSWORD = os.environ.get("MicrosoftAppPassword", "")

    az_openai_key = "xxxxxxxxxxyour -oaoi -endpoinet.openai.azure.com/"
    az_openai_version = "2024-05-01-preview" # required for the assistants API v2
    deployment_name = "gpt4-0"
    # deployment_name = "gpt-4-0125-preview"
    assistant_id = ""
    vector_store_id = ""

    az_application_insights_key = ''