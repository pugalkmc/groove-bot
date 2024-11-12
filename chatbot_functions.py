from collections import deque
from datetime import datetime
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_community.document_loaders import WebBaseLoader, PyPDFLoader
import pinecone
import google.generativeai as genai
import config
from openai import OpenAI

genai.configure(api_key=config.GOOGLE_API_KEY)

# Set up the model
generation_config = {
  "temperature": 1,
  "top_p": 0.95,
  "top_k": 64,
  "max_output_tokens": 8192,
}

safety_settings = [
  {
    "category": "HARM_CATEGORY_HARASSMENT",
    "threshold": "BLOCK_MEDIUM_AND_ABOVE"
  },
  {
    "category": "HARM_CATEGORY_HATE_SPEECH",
    "threshold": "BLOCK_MEDIUM_AND_ABOVE"
  },
  {
    "category": "HARM_CATEGORY_SEXUALLY_EXPLICIT",
    "threshold": "BLOCK_MEDIUM_AND_ABOVE"
  },
  {
    "category": "HARM_CATEGORY_DANGEROUS_CONTENT",
    "threshold": "BLOCK_MEDIUM_AND_ABOVE"
  },
]

system_prompt = f"""
You work as a customer service representative for a firm. Naturally continue the conversation and reply to the user using the details they have given.

Instructions to follow: Be succinct and personable when providing details.
If the user requests it, the most recent information based on the announcement time and present time should be properly linked to the sources.
Your system is internal, so don't reveal your answer if you have trouble answering with the information you've provided.
Try to limit your response to project details and avoid including extraneous material.
Give the user accurate information based on the context and the most recent information you have.
If a customer is searching for something from your business, draw them in.

Steer clear of expressions such as "in this context" or "based on the context provided."
Must Note: Only stick with your company details, never suggest any thing outside or over assume anything to answerback

Current Date and Time: {datetime.now()}
"""

client = OpenAI()
model = genai.GenerativeModel(model_name="gemini-1.5-pro-latest",
                              generation_config=generation_config,
                              safety_settings=safety_settings)

chat_memory = {}

def get_refine_prompt(user_id, text, limit=3):
    if user_id not in chat_memory:
        chat_memory[user_id] = deque(maxlen=limit)

    previous_chat = ""

    for user, system in chat_memory[user_id]:
        previous_chat += f"User: {user}\nAI: {system}\n"
    
    return f"Refine the user message based on the previous chat history\nprevious chat: {previous_chat}\n" \
            f"New user message: {text}\n\nIMPORTANT: Return the refined query string only, no need of any other additional details"

# Step 2: Extract content from Website using WebLoader
def extract_text_from_website(url):
    loader = WebBaseLoader(url)
    documents = loader.load()
    return documents

# Step 3: Chunk the extracted content
def chunk_text(text, chunk_size=600, chunk_overlap=100):
    text_splitter = RecursiveCharacterTextSplitter(chunk_size=chunk_size, chunk_overlap=chunk_overlap)
    return text_splitter.split_documents(text)

def embed_bulk_chunks(chunks, model_name="models/embedding-001", task_type="retrieval_document"):
    try:
        # Create embeddings
        embedding = genai.embed_content(
            model=model_name,
            content=chunks,
            task_type=task_type
        )
        return embedding['embedding']
        
    except Exception as e:
        print(f"An error occurred: {e}")

def perform_search_and_get_chunks(chat_id,index, query_vector, top_k=5):
    try:
        result = index.query(
            vector=query_vector,
            top_k=top_k,
            include_metadata=True,
            namespace=config.settings[chat_id]['manager']
        )

        chunks = []

        for match in result['matches']:
            chunks.append(match['metadata']['source'])

        # print(chunks)
        return  chunks
    except pinecone.core.client.exceptions.PineconeApiException as e:
        print(f"An error occurred: {e}")


def embed_bulk_chunks(chunks, model_name="models/embedding-001", task_type="retrieval_document"):
    try:
        # Create embeddings
        embedding = genai.embed_content(
            model=model_name,
            content=chunks,
            task_type=task_type
        )
        return embedding['embedding']
        
    except Exception as e:
        print(f"An error occurred: {e}")

# Step 6: Use the retrieved chunks to generate an answer with the Gemini model
def generate_answer(retrieved_chunks, query):
    context = "\n\n".join(retrieved_chunks)
    
    # Set up safety settings
    # safety_settings = {
    #     HarmCategory.HARM_CATEGORY_UNSPECIFIED: HarmBlockThreshold.BLOCK_NONE,
    #     HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,
    #     HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
    #     HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
    #     HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
    # }

    # llm = VertexAI(model_name="gemini-1.0-pro-001", safety_settings=safety_settings)
    # prompt = f"Provide answer based on the provided context\nNever say 'belong to the context', 'based on the context', 'provided info'\nThis is a chatbot, should answer to the user relevant, if information does not exist, try to answer basically\nProvide answer more friendly, short and crisp\nContext: {context}\n\nQuestion: {query}\n\nAnswer:"
    prompt_parts = [
        f"input: {query}\ncontext: {context}",
        "output: ",
    ]

    response = model.generate_content(prompt_parts)
    return response.text

def openai_answer(retrieved_chunks, system, user_id, query):
    context = "\n\n".join(retrieved_chunks)

    prompt = f"{system}\n\nProject Details: {context}"
    for chunk in retrieved_chunks:
        prompt += f"{chunk}\n\n"

    history = [{"role":"system", "content": prompt}]
    for user, AI in chat_memory[user_id]:
        history.append({"role": "user", "content": user})
        history.append({"role": "assistant", "content": AI})
    
    history.append({"role": "user", "content": query})
    
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=history
    )
    
    return response.choices[0].message.content
