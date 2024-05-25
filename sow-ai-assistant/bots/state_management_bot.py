from botbuilder.core import ActivityHandler, ConversationState, TurnContext, UserState
from botbuilder.schema import ChannelAccount

# from rpay_chat_bot.user_profile import UserProfile
from data_models.user_profile import UserProfile
from data_models.conversation_data import ConversationData
import time
from datetime import datetime
from openai import AzureOpenAI
from typing_extensions import override
from openai import AssistantEventHandler, OpenAI
import sys
from config import DefaultConfig
import json
import os
from botbuilder.schema import HeroCard, CardAction, ActionTypes, CardImage, Attachment, Activity, ActivityTypes
from botbuilder.core import TurnContext, MessageFactory, CardFactory
import base64
import pyodbc
import inspect
import requests
import openai
import io
from azure.core.credentials import AzureKeyCredential
from azure.search.documents import SearchClient

from PIL import Image
from IPython.display import display
import base64
import glob


class StateManagementBot(ActivityHandler):

    connection = None
    user_response_system_prompt = None
    client =  None
    assistant = None

    def init_meta_prompt() -> any:
        # print("init")
        # read all lines from a text file
        
        with open("metaprompt-1.txt", "r") as file:
            data = file.read().replace("\n", "")
        return data


    def __init__(self, conversation_state: ConversationState, user_state: UserState):
        if conversation_state is None:
            raise TypeError(
                "[StateManagementBot]: Missing parameter. conversation_state is required but None was given"
            )
        if user_state is None:
            raise TypeError(
                "[StateManagementBot]: Missing parameter. user_state is required but None was given"
            )

        self.conversation_state = conversation_state
        self.user_state = user_state
        self.config =  DefaultConfig()

        
        # Create Azure OpenAI client
        if StateManagementBot.client is None:
            print("Creating Azure OpenAI client....")   
            StateManagementBot.client = AzureOpenAI(
                api_key=self.config.az_openai_key,
                azure_endpoint=self.config.az_openai_baseurl,
                api_version=self.config.az_openai_version
            )

        # Run the following lines of code to create a new Assistant and get the assistant id
        #     StateManagementBot.assistant = StateManagementBot.client.beta.assistants.create(
        #     name="Contoso Pre Sales Team Assistant",
        #     instructions=StateManagementBot.init_meta_prompt(),
        #     tools=StateManagementBot.tools,
        #     model=self.config.deployment_name
        # )

        # print('assistant created!',StateManagementBot.assistant.id)
        # # display information about the assistant
        # print(StateManagementBot.assistant.model_dump_json(indent=2))
        print(StateManagementBot.client.beta.assistants.list().model_dump_json(indent=2))



        self.conversation_data_accessor = self.conversation_state.create_property(
            "ConversationData"
        )
        self.user_profile_accessor = self.user_state.create_property("UserProfile")



    def create_vector_database(self) -> str:

        # Create a vector store called "Financial Statements"
        vector_store = StateManagementBot.client.beta.vector_stores.create(name="SOW-Archives")
        
        # Ready the files for upload to OpenAI
        # get me file_paths for each pdf file under the directory data-files
        file_paths = glob.glob("data-files/*.pdf")
        # file_paths = ["mydirectory/myfile1.pdf", "mydirectory/myfile2.txt"]
        file_streams = [open(path, "rb") for path in file_paths]
        
        # Use the upload and poll SDK helper to upload the files, add them to the vector store,
        # and poll the status of the file batch for completion.
        file_batch = StateManagementBot.client.beta.vector_stores.file_batches.upload_and_poll(
        vector_store_id=vector_store.id, files=file_streams
        )
        
        # You can print the status and the file counts of the batch to see the result of this operation.
        print(file_batch.status)
        print(file_batch.file_counts)
        return vector_store.id


    async def on_message_activity(self, turn_context: TurnContext):
        # Get the state properties from the turn context.
        user_profile = await self.user_profile_accessor.get(turn_context, UserProfile)
        conversation_data = await self.conversation_data_accessor.get(
            turn_context, ConversationData
        )

        if user_profile.name is None:
            # First time around this is undefined, so we will prompt user for name.
            if conversation_data.prompted_for_user_name:
                # Set the name to what the user provided.
                user_profile.name = turn_context.activity.text

                conversation_data.chat_history = StateManagementBot.init_meta_prompt()

                # Acknowledge that we got their name.
                await turn_context.send_activity(
                    f"Thanks { user_profile.name }. Let me know how can I help you today"
                )

                # Reset the flag to allow the bot to go though the cycle again.
                conversation_data.prompted_for_user_name = False
            else:
                # Prompt the user for their name.
                await turn_context.send_activity("I am your AI Employee Assistant for Contoso Retail. I can help you quickly get to it!"+\
                                                  "Can you help me with your name?")

                # Set the flag to true, so we don't prompt in the next turn.
                conversation_data.prompted_for_user_name = True
        else:
            # Add message details to the conversation data.
            conversation_data.timestamp = self.__datetime_from_utc_to_local(
                turn_context.activity.timestamp
            )
            conversation_data.channel_id = turn_context.activity.channel_id

            l_thread = conversation_data.thread

            if conversation_data.thread is None:
                # Create a thread
                conversation_data.thread = StateManagementBot.client.beta.threads.create()
                l_thread = conversation_data.thread
                # Threads have an id as well
                print('Session not available for this user, creating one!')
                print("Created thread bearing Thread id: ", conversation_data.thread.id)
 
            # Add a user question to the thread
            message = StateManagementBot.client.beta.threads.messages.create(
                thread_id=l_thread.id,
                role="user",
                content=turn_context.activity.text
            )
            print("Created message bearing Message id: ", message.id)

            # Show the messages
            thread_messages = StateManagementBot.client.beta.threads.messages.list(l_thread.id)
            print('list of all messages: \n',thread_messages.model_dump_json(indent=2))

            # Use this when streaming is not required
            # response_msg = StateManagementBot.get_file_search_response(l_thread.id, self.config.assistant_id)
            await turn_context.send_activity(
                        f"{ user_profile.name } : { StateManagementBot.get_file_search_response(l_thread.id, self.config.assistant_id) }"
                    )

            # Use this when streaming is required
            # response_msg = StateManagementBot.stream_file_search_response(l_thread.id, self.config.assistant_id)
            # activity = await turn_context.send_activity(Activity(text="Processing..."))
            # activity_id = activity.id
            # text_value = ''
            # for event in StateManagementBot.stream_file_search_response(l_thread.id, self.config.assistant_id):
            # # process event here and send response back to the bot user
            #  if hasattr(event.data, 'delta') and hasattr(event.data.delta, 'content'):
            #     # Extract the text value and send it back to the bot user
            #     text_value += event.data.delta.content[0].text.value
            #     # await turn_context.send_activity(Activity(text=text_value))
            #     await turn_context.send_activity(Activity(id=activity_id,text=text_value))

            return
    
    def role_icon(role):
        if role == "user":
            return "👤"
        elif role == "assistant":
            return "🤖"


    # function to get the file search response, by streaming the response
    def stream_file_search_response(thread_id, assistant_id):
        with StateManagementBot.client.beta.threads.runs.stream(
            thread_id=thread_id,
            assistant_id=assistant_id,
            event_handler=EventHandler(),
        ) as stream:
            for event in stream:
                yield event

    # function to get the file search response, without streaming the response
    def get_file_search_response(thread_id, assistant_id):
        run = StateManagementBot.client.beta.threads.runs.create_and_poll(
            thread_id=thread_id, assistant_id=assistant_id
        )

        messages = list(StateManagementBot.client.beta.threads.messages.list(thread_id=thread_id, run_id=run.id))

        message_content = messages[0].content[0].text
        print('the number of citations are :',len(message_content.annotations))
        annotations = message_content.annotations
        citations = []
        for index, annotation in enumerate(annotations):
            message_content.value = message_content.value.replace(annotation.text, f"[{index}]")
            if file_citation := getattr(annotation, "file_citation", None):
                cited_file = StateManagementBot.client.files.retrieve(file_citation.file_id)
                citations.append(f"[{index}] {cited_file.filename}")

        print('message content ----> \n',message_content.value)
        print('the citations are below \n',citations)
        return message_content.value +  "\n".join(citations)

    # function returns the run when status is no longer queued or in_progress
    def wait_for_run(run, thread_id):
        while run.status == 'queued' or run.status == 'in_progress':
            run = StateManagementBot.client.beta.threads.runs.retrieve(
                    thread_id=thread_id,
                    run_id=run.id
            )
            print("Run status:", run.status)
            time.sleep(0.5)

        return run
    


    



    async def on_turn(self, turn_context: TurnContext):
        await super().on_turn(turn_context)

        await self.conversation_state.save_changes(turn_context)
        await self.user_state.save_changes(turn_context)

    def __datetime_from_utc_to_local(self, utc_datetime):
        now_timestamp = time.time()
        offset = datetime.fromtimestamp(now_timestamp) - datetime.utcfromtimestamp(
            now_timestamp
        )
        result = utc_datetime + offset
        return result.strftime("%I:%M:%S %p, %A, %B %d of %Y")
    

    tools = [
        {
            "type": "code_interpreter",  # should be set to retrieval but that is not supported yet; required or file_ids will throw error
        },
        {
            "type": "file_search"
        }
    ]



    # helper method used to check if the correct arguments are provided to a function
    def check_args(function, args):
        print('checking function parameters')
        sig = inspect.signature(function)
        params = sig.parameters
        # Check if there are extra arguments
        for name in args:
            if name not in params:
                return False
        # Check if the required arguments are provided
        for name, param in params.items():
            if param.default is param.empty and name not in args:
                return False

        return True


class EventHandler(AssistantEventHandler):
    @override
    def on_text_created(self, text) -> None:
        print(f"\nassistant > ", end="", flush=True)

    @override
    def on_tool_call_created(self, tool_call):
        print(f"\nassistant > {tool_call.type}\n", flush=True)

    @override
    def on_message_done(self, message) -> None:
        # print a citation to the file searched
        message_content = message.content[0].text
        annotations = message_content.annotations
        citations = []
        for index, annotation in enumerate(annotations):
            message_content.value = message_content.value.replace(
                annotation.text, f"[{index}]"
            )
            if file_citation := getattr(annotation, "file_citation", None):
                cited_file = StateManagementBot.client.files.retrieve(file_citation.file_id)
                citations.append(f"[{index}] {cited_file.filename}")

        print(message_content.value)
        print("\n".join(citations))