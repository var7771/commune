import commune as c
import os
import getpass
from langchain.document_loaders import TextLoader
from langchain.embeddings.openai import OpenAIEmbeddings
from langchain.text_splitter import CharacterTextSplitter
from langchain.vectorstores import Chroma
from typing import Union, List, Any, Dict
import sqlite3
import numpy as np
from sklearn.metrics.pairwise import cosine_similarity
from sentence_transformers import SentenceTransformer

__import__('pysqlite3')
import sys
sys.modules['sqlite3'] = sys.modules.pop('pysqlite3')

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': 'db.sqlite3',
    }
}

class DatabaseManager:
    def __init__(self, db_name):
        self.conn = sqlite3.connect(db_name)
        self.cursor = self.conn.cursor()
        self.create_table()

    def create_table(self):
        self.cursor.execute('''CREATE TABLE IF NOT EXISTS embeddings
                     (sentence text, embedding text)''')

    def insert_embedding(self, sentence, embedding):
        self.cursor.execute("INSERT INTO embeddings VALUES (?,?)", (sentence, str(list(embedding))))
        self.conn.commit()

    def update_embedding(self, sentence, new_embedding):
        self.cursor.execute("UPDATE embeddings SET embedding = ? WHERE sentence = ?", (str(list(new_embedding)), sentence))
        self.conn.commit()

    def delete_embedding(self, sentence):
        self.cursor.execute("DELETE FROM embeddings WHERE sentence = ?", (sentence,))
        self.conn.commit()

    def fetch_embedding(self, sentence):
        self.cursor.execute("SELECT * FROM embeddings WHERE sentence = ?", (sentence,))
        return self.cursor.fetchone()

    def fetch_all_embeddings(self):
        self.cursor.execute('SELECT * FROM embeddings')
        return self.cursor.fetchall()

class EmbeddingModel:
    def __init__(self, model_name):
        self.model = SentenceTransformer(model_name)

    def get_embedding(self, sentence):
        return self.model.encode([sentence])[0]

class SentenceManager:
    def __init__(self, db_manager, embedding_model):
        self.db_manager = db_manager
        self.embedding_model = embedding_model

    def add_sentence(self, sentence):
        embedding = self.embedding_model.get_embedding(sentence)
        self.db_manager.insert_embedding(sentence, embedding)
        return {'msg': f"Sentence is added to local vector store.", 'success': True}

    def update_sentence(self, sentence):
        new_embedding = self.embedding_model.get_embedding(sentence)
        self.db_manager.update_embedding(sentence, new_embedding)
        return {'msg': f"Sentence is updated from local vector store.", 'success': True}

    def delete_sentence(self, sentence):
        self.db_manager.delete_embedding(sentence)
        return {'msg': f"Sentence is deleted from local vector store.", 'success': True}

    def get_sentence_embedding(self, sentence):
        return self.db_manager.fetch_embedding(sentence)

    def prompt(self, query):
        query_embedding = self.embedding_model.get_embedding(query)
        rows = self.db_manager.fetch_all_embeddings()
        return max(rows, key=lambda row: cosine_similarity([query_embedding], [np.array(eval(row[1]))]))[0]

db_manager = DatabaseManager('embeddings.db')
embedding_model = EmbeddingModel('all-MiniLM-L6-v2')
sentence_manager = SentenceManager(db_manager, embedding_model)

class ModelVectorstore(c.Module):
    def __init__(self, config = None, **kwargs):
        self.set_config(config, kwargs=kwargs)

    def call(self, x:int = 1, y:int = 2) -> int:
        c.print(self.config.sup)
        c.print(self.config, 'This is the config, it is a Munch object')
        return x + y
    
    def search(self, api_key, path="./commune/modules/model/vectorstore/state_of_the_union.txt", query="What did the president say about Ketanji Brown Jackson"):
        os.environ['OPENAI_API_KEY'] = api_key

        if (path == "./commune/modules/model/vectorstore/state_of_the_union.txt"):
            print("\033[93m" + "The result will be generated by test conversation script." + "\033[0m")

        if (query == "What did the president say about Ketanji Brown Jackson"):
            print("\033[93m" + "The result will be generated by test query." + "\033[0m")

        # Load the document, split it into chunks, embed each chunk and load it into the vector store.
        raw_documents = TextLoader(path).load()
        text_splitter = CharacterTextSplitter(chunk_size=1000, chunk_overlap=0)
        documents = text_splitter.split_documents(raw_documents)
        db = Chroma.from_documents(documents, OpenAIEmbeddings())

        docs = db.similarity_search(query)
        return docs[0].page_content 

    @classmethod
    def random_api_key(cls):
        api_keys = cls.api_keys()
        assert len(api_keys) > 0, "No valid API keys found, please add one via ```c openai add_api_key <api_key>```"
        api_key = c.choice(api_keys)

        return api_key
  
    def set_api_key(self, api_key: str = None) -> str:
        if api_key==None and  len(self.keys()) > 0 :
            api_key = self.random_api_key()
        self.api_key = api_key
        os.environ['OPENAI_API_KEY'] = self.api_key
        return {'msg': f"API Key set to {api_key}", 'success': True}

    @classmethod
    def add_key(cls, api_key:str):
        assert isinstance(api_key, str), "API key must be a string"
        api_keys = list(set(cls.get('api_keys', []) + [api_key]))
        cls.put('api_keys', api_keys)
        return {'msg': f"API Key set to {api_key}", 'success': True}
    
    @classmethod
    def rm_key(cls, api_key:str):
        new_keys = []
        api_keys = cls.api_keys()
        for k in api_keys: 
            if api_key in k:
                continue
            else:
                new_keys.append(k)
        cls.put('api_keys', new_keys)
        return {'msg': f"Removed API Key {api_key}", 'success': True}
                
    
    @classmethod
    def api_keys(cls):
        return  cls.get('api_keys', [])
    
    @classmethod
    def save_api_keys(cls, api_keys:List[str]):
        cls.put('api_keys', api_keys)
        return {'msg': f"Saved API Keys", 'success': True}

    def add_sentence(self, sentence):
        return sentence_manager.add_sentence(sentence)

    def prompt(self, query):
        result = sentence_manager.prompt(query)
        return {'result': result, 'success': True}
