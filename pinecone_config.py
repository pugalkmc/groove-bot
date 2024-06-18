from pinecone import Pinecone, ServerlessSpec
import config

INDEX_NAME = "common"
BATCH_SIZE = 1000
DIMENSION = 768

def pinecone_setup():
    pc = Pinecone(api_key=config.PINECONE_API_KEY)
    # Initialize the Pinecone client
    if INDEX_NAME not in pc.list_indexes().names():
        pc.create_index(INDEX_NAME, dimension=DIMENSION, spec=ServerlessSpec(cloud='aws', region='us-east-1'))
    return pc.Index(INDEX_NAME)

index = pinecone_setup()

def delete_with_tag(tag):
    try:
        # Get all document IDs (for efficiency)
        all_ids = index.scan(include_metadata=False)['ids']
        
        # Filter matching IDs based on metadata
        filtered_ids = [
            doc_id for doc_id in all_ids 
            if index.get(doc_id, include_metadata=True)['metadata']['tag'] == tag
        ]
        
        if filtered_ids:
            index.delete(ids=filtered_ids)
            print(f"Deleted {len(filtered_ids)} documents with tag '{tag}'.")
        else:
            print(f"No documents found with tag '{tag}'.")
    
    except Exception as e:
        print(f"An error occurred: {e}")
