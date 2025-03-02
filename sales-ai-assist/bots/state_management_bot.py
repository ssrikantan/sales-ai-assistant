from botbuilder.core import ActivityHandler, ConversationState, TurnContext, UserState
from botbuilder.schema import ChannelAccount

from data_models.user_profile import UserProfile
from data_models.conversation_data import ConversationData
import time
from datetime import datetime
from openai import AzureOpenAI
from typing_extensions import override
from openai import AssistantEventHandler, OpenAI

from config import DefaultConfig
import json

from botbuilder.schema import Attachment, Activity, ActivityTypes
from botbuilder.core import TurnContext, MessageFactory, CardFactory
import base64
import glob


class StateManagementBot(ActivityHandler):

    connection = None
    user_response_system_prompt = None
    client =  None
    assistant = None
    tools = [
        {
            "type": "code_interpreter"
        },
        {
            "type": "file_search"
        }
    ]


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
        self.client = AzureOpenAI(
                api_key=self.config.az_openai_key,
                azure_endpoint=self.config.az_openai_baseurl,
                api_version=self.config.az_openai_version
            )
        self.conversation_data_accessor = self.conversation_state.create_property(
            "ConversationData"
        )
        self.user_profile_accessor = self.user_state.create_property("UserProfile")

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

                # Acknowledge that we got their name.
                await turn_context.send_activity(
                    f"Thanks { user_profile.name }. Let me know how can I help you today"
                )

                # Reset the flag to allow the bot to go though the cycle again.
                conversation_data.prompted_for_user_name = False
            else:
                # Prompt the user for their name.
                await turn_context.send_activity("I am your AI Assistant for Sales. I can help you quickly get to it!"+\
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
                conversation_data.thread = self.client.beta.threads.create()
                l_thread = conversation_data.thread
                # Threads have an id as well
                print('Session not available for this user, creating one!')
                print("Created thread bearing Thread id: ", conversation_data.thread.id)
 
            # Add a user question to the thread
            message = self.client.beta.threads.messages.create(
                thread_id=l_thread.id,
                role="user",
                content=turn_context.activity.text
            )
            print("Created message bearing Message id: ", message.id)

            # Show the messages
            thread_messages = self.client.beta.threads.messages.list(l_thread.id)
            print('list of all messages: \n',thread_messages.model_dump_json(indent=2))

        #     run = self.client.beta.threads.runs.create_and_poll(
        #     thread_id=l_thread.id, assistant_id=self.config.assistant_id
        # )
        # The above method was not working consistently, 
        # hence polling the run status manually below

            run = self.client.beta.threads.runs.create(
            thread_id=l_thread.id, assistant_id=self.config.assistant_id
        )

            run = self.wait_for_run(run, l_thread.id)
            if run.status == 'failed':
                print('run has failed, extracting results ...')
                print('the thread run has failed !! \n',run.model_dump_json(indent=2))
                return await turn_context.send_activity(
                        f"{ user_profile.name } : { 'Sorry, I am unable to process your request at the moment. Please try again later.' }"
                    )
            print('run has completed, extracting results ...')
            print('the thread has run!! \n',run.model_dump_json(indent=2))

            messages = self.client.beta.threads.messages.list(thread_id=l_thread.id)
            print('Messages are **** \n',messages.model_dump_json(indent=2))

            # Use this when streaming is not required
            messages_json = json.loads(messages.model_dump_json())
            print('response messages_json>\n',messages_json)
            action_response_to_user = ''
            file_content = None
            file_id = ''
            image_data_bytes = None

            for item in messages_json['data']:
                # Check the content array
                for content in item['content']:
                    # If there is text in the content array, print it
                    if 'text' in content:
                        action_response_to_user = content['text']['value'] + "\n"
                    # If there is an image_file in the content, print the file_id
                    if 'image_file' in content:
                        print("Image ID:" , content['image_file']['file_id'], "\n")
                        file_id = content['image_file']['file_id']
                        file_content = self.client.files.content(file_id)
                        image_data_bytes = file_content.read()
                break

            if image_data_bytes is not None:
                reply = Activity(type=ActivityTypes.message)
                reply.text = action_response_to_user
                file_path = file_id+".png"
                base64_image = base64.b64encode(image_data_bytes).decode()
                
                # Create an attachment with the base64 image
                attachment = Attachment(
                    name=file_id+".png",
                    content_type="image/png",
                    content_url=f"data:image/png;base64,{base64_image}"
                )
                reply.attachments = [attachment]
                return await turn_context.send_activity(reply)
            else:
                return await turn_context.send_activity(
                        f"{ user_profile.name } : { action_response_to_user }"
                    )
    # function returns the run when status is no longer queued or in_progress
    def wait_for_run(self, run, thread_id):
        while run.status == 'queued' or run.status == 'in_progress':
            run = self.client.beta.threads.runs.retrieve(
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

    def create_vector_database(self) -> str:

        # Create a vector store called "SOW-Archives-v1"
        vector_store = self.client.beta.vector_stores.create(name="SOW-Archives-v1")
        # Ready the files for upload to OpenAI
        # get me file_paths for each pdf file under the directory data-files
        file_paths = glob.glob("data-files/*.pdf")
        # file_paths = ["mydirectory/myfile1.pdf", "mydirectory/myfile2.txt"]
        file_streams = [open(path, "rb") for path in file_paths]
        
        # Use the upload and poll SDK helper to upload the files, add them to the vector store,
        # and poll the status of the file batch for completion.
        file_batch = self.client.beta.vector_stores.file_batches.upload_and_poll(
        vector_store_id=vector_store.id, files=file_streams
        )
        
        # You can print the status and the file counts of the batch to see the result of this operation.
        print(file_batch.status)
        print(file_batch.file_counts)
        print('new vector database created ',vector_store.id)
        self.client.beta.assistants.update(
            assistant_id=self.config.assistant_id,
            tool_resources={"file_search": {"vector_store_ids": [self.config.vector_store_id]}},
        )
        return vector_store.id

    def update_vector_database(self):
        # get me file_paths for each pdf file under the directory data-files
        file_paths = glob.glob("data-files/*.pdf")
        # file_paths = ["mydirectory/myfile1.pdf", "mydirectory/myfile2.txt"]
        file_streams = [open(path, "rb") for path in file_paths]
        
        # Use the upload and poll SDK helper to upload the files, add them to the vector store,
        # and poll the status of the file batch for completion.
        file_batch = self.client.beta.vector_stores.file_batches.upload_and_poll(
        vector_store_id=self.config.vector_store_id, files=file_streams
        )
        
        # You can print the status and the file counts of the batch to see the result of this operation.
        print(file_batch.status)
        print(file_batch.file_counts)
        self.client.beta.assistants.update(
            assistant_id=self.config.assistant_id,
            tool_resources={"file_search": {"vector_store_ids": [self.config.vector_store_id]}},
        )
