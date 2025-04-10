# -*- coding: utf-8 -*-
"""taxonomy-completion-with-embedding-quantization-and-llms.ipynb

Automatically generated by Colab.

Original file is located at
    https://colab.research.google.com/drive/1IqK2USRg47EvTdQBG1rp7Hj1UKI9iqtG
"""

# Commented out IPython magic to ensure Python compatibility.
# %pip install altair datasets hdbscan umap-learn sentence-transformers --quiet

!pip install opencv-python --quiet

from sentence_transformers import SentenceTransformer
model = SentenceTransformer('jinaai/jina-embeddings-v2-base-en', trust_remote_code=True)

from datasets import load_dataset

ds = load_dataset("saidonepudi8/dental_tc", split="train")
ds

corpus = [f"{title}: {abstract}. Keywords: {keywords}" for title, abstract, keywords in zip(ds['Title'], ds['Abstract'], ds['keywords from documents supplied by authors'])]
f32_embeddings = model.encode(corpus,
                              batch_size=64,
                              show_progress_bar=True)

f32_embeddings.shape, f32_embeddings.dtype

# Save the embeddings
import numpy as np
np.save('f32_embeddings.npy', f32_embeddings)

# Load your embeddings
f32_embeddings = np.load('f32_embeddings.npy')
f32_embeddings.shape, f32_embeddings.dtype

import matplotlib.pyplot as plt

# Flatten the embeddings and plot histogram
plt.hist(f32_embeddings.flatten(), bins=250, edgecolor='C0')
plt.xlabel('Float32 Embeddings')
plt.title('Embeddings Distribution')
plt.show()

# Print min and max values
print("Min value:", np.min(f32_embeddings), "Max value:", np.max(f32_embeddings))

def calibration_accuracy(embeddings: np.ndarray, k: int = 10000) -> float:
    calibration_embeddings = embeddings[:k]
    f_min = np.min(calibration_embeddings, axis=0)
    f_max = np.max(calibration_embeddings, axis=0)

    # Calculate percentage in range for each dimension
    size = embeddings.shape[0]
    avg = []
    for i in range(embeddings.shape[1]):
        in_range = np.sum((embeddings[:, i] >= f_min[i]) & (embeddings[:, i] <= f_max[i]))
        dim_percentage = (in_range / size) * 100
        avg.append(dim_percentage)

    return np.mean(avg)

acc = calibration_accuracy(f32_embeddings, k=10000)
print(f"Average percentage of embeddings within [f_min, f_max] calibration: {acc:.5f}%")

from sentence_transformers.quantization import quantize_embeddings

# Quantize embeddings to int8
int8_embeddings = quantize_embeddings(
    np.array(f32_embeddings),
    precision="int8",
    calibration_embeddings=np.array(f32_embeddings[:10000]),
)

f32_embeddings.dtype, f32_embeddings.shape, f32_embeddings.nbytes, (np.max(f32_embeddings), np.min(f32_embeddings))

int8_embeddings.dtype, int8_embeddings.shape, int8_embeddings.nbytes, (np.max(int8_embeddings), np.min(int8_embeddings))

# calculate compression
(f32_embeddings.nbytes - int8_embeddings.nbytes) / f32_embeddings.nbytes * 100

def scalar_quantize_embeddings(embeddings: np.ndarray,
                               calibration_embeddings: np.ndarray) -> np.ndarray:
    """
    Quantize embeddings into uint8 using scalar quantization based on calibration embeddings.

    Parameters:
    embeddings (numpy.ndarray): The floating-point embedding vectors to be quantized.
    calibration_embeddings (numpy.ndarray): The floating-point calibration embedding vectors.

    Returns:
    np.ndarray: quantized embeddings
    """
    # Step 1: Calculate [f_min, f_max] per dimension from the calibration set
    f_min = np.min(calibration_embeddings, axis=0)
    f_max = np.max(calibration_embeddings, axis=0)

    # Step 2: Map [f_min, f_max] to [q_min, q_max] => (scaling factors, zero point)
    q_min = 0
    q_max = 255
    scales = (f_max - f_min) / (q_max - q_min)
    zero_point = 0 # uint8 quantization maps inherently min_values to zero, added for completeness

    # Step 3: encode (scale, round)
    quantized_embeddings = ((embeddings - f_min) / scales).astype(np.uint8)

    return quantized_embeddings

calibration_embeddings = f32_embeddings[:10000]
beta_uint8_embeddings = scalar_quantize_embeddings(f32_embeddings, calibration_embeddings)

np.min(beta_uint8_embeddings), np.max(beta_uint8_embeddings)

beta_uint8_embeddings[10][64:128].reshape(8, 8)

embeddings = int8_embeddings

import umap

# Reduce to 5 dimensions for clustering
reducer_5d = umap.UMAP(n_neighbors=100,
                       n_components=5,
                       min_dist=0.1,
                       metric='cosine',
                       random_state=42)
embedding_5d = reducer_5d.fit_transform(f32_embeddings)

# Reduce to 2 dimensions for visualization
reducer_2d = umap.UMAP(n_neighbors=100,
                       n_components=2,
                       min_dist=0.1,
                       metric='cosine',
                       random_state=42)
embedding_2d = reducer_2d.fit_transform(f32_embeddings)

import hdbscan

clusterer = hdbscan.HDBSCAN(min_cluster_size=15,
                            metric='euclidean',
                            min_samples=10,
                            cluster_selection_method='leaf')
clusters = clusterer.fit_predict(embedding_5d)

import pandas as pd

# Convert your dataset to a Pandas DataFrame
df = ds.to_pandas()

# Add the 2D embeddings and cluster labels to the DataFrame
df['x'] = embedding_2d[:, 0]
df['y'] = embedding_2d[:, 1]
df['cluster'] = clusters

# Remove outliers (optional)
df = df[df['cluster'] != -1]

# Display the first few rows
df[['x', 'y', 'cluster', 'Title', 'Abstract', 'keywords from documents supplied by authors']].head()

df

import altair as alt

chart = alt.Chart(df).mark_circle(size=60).encode(
    x='x',
    y='y',
    color='cluster:N',
    tooltip=['Title', 'cluster', 'Abstract', 'keywords from documents supplied by authors']
).properties(
    width=800,
    height=600
).interactive()

chart

num_clusters = df['cluster'].nunique()
print(f"Number of clusters: {num_clusters}")

# Group by clusters and list titles, abstracts, and keywords
cluster_groups = df.groupby('cluster').apply(lambda x: x[['Title', 'Abstract', 'keywords from documents supplied by authors']].to_dict(orient='records'))

# Example: Print titles, abstracts, and keywords from a specific cluster
cluster_id = 0  # Change to the cluster you're interested in
print(f"Entries in cluster {cluster_id}:")
for entry in cluster_groups[cluster_id]:
    print("- Title:", entry['Title'])
    print("  Abstract:", entry['Abstract'])
    print("  Keywords:", entry['keywords from documents supplied by authors'])
    print()

# Adjust UMAP parameters
reducer = umap.UMAP(n_neighbors=50,  # Try different values
                    n_components=2,
                    min_dist=0.05,
                    metric='cosine',
                    random_state=42)
embedding_2d = reducer.fit_transform(f32_embeddings)

# Adjust HDBSCAN parameters
clusterer = hdbscan.HDBSCAN(min_cluster_size=50,  # Try different values
                            metric='euclidean',
                            cluster_selection_method='eom')
clusters = clusterer.fit_predict(embedding_2d)

df.to_csv('clustered_data.csv', index=False)

# Commented out IPython magic to ensure Python compatibility.
# %pip install huggingface_hub langchain langchain_huggingface langchain_community openai --upgrade --quiet

from pydantic import BaseModel, Field
from typing import List, Dict, Any

class Topic(BaseModel):
    label: str = Field(..., description="Identified topic")

from langchain_core.prompts import PromptTemplate

topic_prompt = """
You are a helpful Research Engineer. Your task is to analyze a set of research paper metadata(such as titles, abstracts, and keywords) related to Dentistry and
determine the single overarching topic of the cluster. Based on the titles, abstracts, and keywords from documents supplied by the author provided, you should identify and label the most relevant topic.
Please output the topic name directly and clearly.

EXPECTED OUTPUT:
Topic: Topic Name

TITLES:
{titles}
ABSTRACTS:
{abstracts}
KEYWORDS:
{keywords}
"""

import os
from google.colab import userdata
os.environ["HUGGINGFACEHUB_API_TOKEN"] = userdata.get('HUGGINGFACEHUB_API_TOKEN')
os.environ["OPENAI_API_KEY"] = userdata.get('OPENAI_API_KEY')

import os
import re
import json
from langchain.chains import LLMChain
from huggingface_hub import InferenceClient
from langchain_huggingface import HuggingFaceEndpoint
from langchain_core.output_parsers import PydanticOutputParser

from typing import List

# Helper function to batch process entries
def batch_entries(entries: List[Dict[str, Any]], batch_size: int) -> List[List[Dict[str, Any]]]:
    """
    Split the entries into smaller batches to avoid exceeding token limits.
    """
    for i in range(0, len(entries), batch_size):
        yield entries[i:i + batch_size]

def TopicModelingMistral(entries: List[dict], batch_size: int = 5) -> str:
    # Initialize the InferenceClient
    inference_client = InferenceClient()

    topics = []
    for batch in batch_entries(entries, batch_size):
        combined_text = {
            "titles": "\n".join([entry["Title"] for entry in batch]),
            "abstracts": "\n".join([entry["Abstract"] for entry in batch]),
            "keywords": "\n".join([entry["keywords from documents supplied by authors"] for entry in batch])
        }

        # Specify the model explicitly and use the text-generation task
        response = inference_client.text_generation(
            model="mistralai/Mistral-7B-Instruct-v0.3",
            inputs=f"{topic_prompt}\nTITLES:\n{combined_text['titles']}\n\nABSTRACTS:\n{combined_text['abstracts']}\n\nKEYWORDS:\n{combined_text['keywords']}",
            parameters={"temperature": 0.2}
        )

        try:
            # Extract the topic from the response
            topic = response['generated_text'].strip()
            topics.append(topic)
        except Exception as e:
            print(f"Error parsing output: {e}")
            topics.append("Unknown Topic")

    final_topic = topics[0] if topics else "Unknown Topic"
    return final_topic

# Generate topics for each cluster
topics_mistral = []

for cluster_id, cluster in df.groupby('cluster'):
    entries = cluster[['Title', 'Abstract', 'keywords from documents supplied by authors']].to_dict(orient='records')

    try:
        topic_mistral = TopicModelingMistral(entries)
        print(f"Generated Topic for cluster {cluster_id}: {topic_mistral}")
        topics_mistral.append((cluster_id, topic_mistral))
    except Exception as e:
        print(f"Error with Mistral on cluster {cluster_id}: {e}")
        topics_mistral.append((cluster_id, "Unknown Topic"))

# Map the topics back to the DataFrame
topic_map_mistral = dict(topics_mistral)
df['topic_mistral'] = df['cluster'].map(topic_map_mistral)

# Display the topic assignments
print(df[['cluster', 'topic_mistral']])

df

from langchain.chat_models.openai import ChatOpenAI
import time


def extract_topic(output: str) -> str:
    """
    Extract the topic from the text output using regex.
    """
    topic_str = re.search(r'Topic:\s*(.*)', output)
    if topic_str:
        return topic_str.group(1).strip()
    else:
        raise ValueError("No valid topic found in the output")

def TopicModelingGPT4Batched(entries: List[dict], batch_size: int = 5) -> str:
    openai_api_key = os.getenv('OPENAI_API_KEY')
    llm = ChatOpenAI(model='gpt-4', temperature=0.1, max_tokens=100, openai_api_key=openai_api_key)
    prompt = PromptTemplate.from_template(topic_prompt)

    topics = []
    for batch in batch_entries(entries, batch_size):
        combined_text = {
            "titles": "\n".join([entry["Title"] for entry in batch]),
            "abstracts": "\n".join([entry["Abstract"] for entry in batch]),
            "keywords": "\n".join([entry["keywords from documents supplied by authors"] for entry in batch])
        }

        topic_chain = LLMChain(llm=llm, prompt=prompt)

        for _ in range(3):  # Retry logic: attempt up to 3 times
            try:
                raw_output = topic_chain.run(combined_text)
                topic = extract_topic(raw_output)  # Extract the topic from the output
                topics.append(topic)
                break
            except Exception as e:
                if "quota" in str(e).lower():
                    print(f"Quota exceeded. Retrying in 60 seconds...")
                    time.sleep(60)
                else:
                    print(f"Error parsing output: {e}")
                    topics.append("Unknown Topic")
                    break

    # Take the most representative topic (e.g., the first one) or deduplicate
    final_topic = list(set(topics))  # Remove duplicates
    return final_topic[0] if final_topic else "Unknown Topic"

# Generate topics for each cluster using GPT-4
topics_gpt = []

for cluster_id, cluster in df.groupby('cluster'):
    entries = cluster[['Title', 'Abstract', 'keywords from documents supplied by authors']].to_dict(orient='records')

    try:
        topic_gpt = TopicModelingGPT4Batched(entries)
        print(f"Generated Topic for cluster {cluster_id}: {topic_gpt}")
        topics_gpt.append((cluster_id, topic_gpt))
    except Exception as e:
        print(f"Error with GPT-4 on cluster {cluster_id}: {e}")
        topics_gpt.append((cluster_id, "Unknown Topic"))

# Map the topics back to the DataFrame
topic_map_gpt = dict(topics_gpt)

df['topic_gpt'] = df['cluster'].map(topic_map_gpt)

# Display the topic assignments
print(df[['cluster', 'topic_gpt']].drop_duplicates(subset='cluster'))

# Extract topics from the tuple
topic_map_mistral_corrected = {cluster_id: topic for cluster_id, topic in topics_mistral}
topic_map_gpt_corrected = {cluster_id: topic for cluster_id, topic in topics_gpt}

# Map the topics back to the DataFrame
df['topic_mistral'] = df['cluster'].map(topic_map_mistral_corrected)
df['topic_gpt'] = df['cluster'].map(topic_map_gpt_corrected)

# Display the DataFrame with the corrected topic assignments
print(df[['cluster', 'topic_mistral', 'topic_gpt']].drop_duplicates(subset='cluster'))

df = pd.read_csv('/content/topics.csv')
df

!pip install "vl-convert-python>=1.6.0"

!pip install "vegafusion[embed]>=1.5.0"

import altair as alt
alt.data_transformers.enable("vegafusion")

df

import altair as alt

custom_color_palette = [
    '#1f77b4', '#aec7e8', '#ff7f0e', '#ffbb78', '#2ca02c',
    '#98df8a', '#d62728', '#ff9896', '#9467bd', '#c5b0d5',
    '#8c564b', '#c49c94', '#e377c2', '#f7b6d2', '#7f7f7f',
    '#c7c7c7', '#bcbd22', '#dbdb8d', '#17becf', '#9edae5',
    '#393b79', '#5254a3', '#6b6ecf', '#9c9ede', '#637939',
    '#8ca252', '#b5cf6b', '#cedb9c', '#8c6d31', '#bd9e39',
    '#e7ba52', '#e7cb94', '#843c39', '#ad494a', '#d6616b'
]

# Create the chart with additional tooltip information
chart = alt.Chart(df).mark_circle(size=5).encode(
    x='x',
    y='y',
    color=alt.Color('topic_gpt:N', scale=alt.Scale(range=custom_color_palette)),
    tooltip=['Title', 'Abstract', 'keywords from documents supplied by authors', 'topic_gpt']
).interactive().properties(
    title='Dental (topic_gpt)',
    width=600,
    height=400,
)

# Display the chart
chart.display()

import altair as alt

custom_color_palette = [
    '#1f77b4', '#aec7e8', '#ff7f0e', '#ffbb78', '#2ca02c',
    '#98df8a', '#d62728', '#ff9896', '#9467bd', '#c5b0d5',
    '#8c564b', '#c49c94', '#e377c2', '#f7b6d2', '#7f7f7f',
    '#c7c7c7', '#bcbd22', '#dbdb8d', '#17becf', '#9edae5',
    '#393b79', '#5254a3', '#6b6ecf', '#9c9ede', '#637939',
    '#8ca252', '#b5cf6b', '#cedb9c', '#8c6d31', '#bd9e39',
    '#e7ba52', '#e7cb94', '#843c39', '#ad494a', '#d6616b'
]

chart_mistral = alt.Chart(df).mark_circle(size=60).encode(
    x='x:Q',
    y='y:Q',
    color=alt.Color('topic_mistral:N', scale=alt.Scale(range=custom_color_palette)),
    tooltip=['Title', 'Abstract', 'keywords from documents supplied by authors', 'topic_mistral']
).interactive().properties(
    title='Dental (Mistral)',
    width=600,
    height=400,
)

# Display the chart
chart_mistral.display()

# Count the frequency of each topic pair (Mistral, GPT-4)
topic_counts = df[['topic_mistral', 'topic_gpt']].value_counts()
print(topic_counts)

df

# Get unique GPT-4 topics
unique_gpt_topics = df['topic_gpt'].unique()
print(unique_gpt_topics)

# Get unique Mistral topics
unique_mistral_topics = df['topic_mistral'].unique()
print(unique_mistral_topics)

!pip install langchain

!pip install --upgrade langchain langchain_huggingface

subtopics = df['topic_gpt'].unique().tolist()
subtopics_text = '\n'.join(subtopics)
print(subtopics_text)

df

df.to_csv('topics.csv', index=False)

from langchain.prompts import PromptTemplate
from langchain.chains import LLMChain
from langchain.chat_models import ChatOpenAI

# Define the taxonomy prompt
taxonomy_prompt = """
You are an expert and a genius in dental research and clinical practice. Your task is to create an extremely detailed and granular taxonomy for a dentistry-related dataset. The final taxonomy should capture the diversity of dental research, clinical procedures, digital innovations, dental education, and healthcare practices by organizing them into at least **fifteen levels** of hierarchy.

**Main Objective:**
Analyze the provided **SUBTOPICS**, **TITLES**, **ABSTRACTS**, and **KEYWORDS** from dental research papers. Your goal is to extract, categorize, and hierarchically structure dental-specific terms into a taxonomy that includes:
- **Level 1:** Main categories (e.g., Dental Informatics, Digital Dentistry, Dental Healthcare).
- **Level 2:** Broad subcategories within each main category (e.g., Electronic Health Records, 3D Technologies, Preventive Dentistry, etc.)
- **Level 3:** More specific divisions or clusters under each subcategory (e.g., Data Management, Prosthetics Fabrication, Preventive Dentistry)
- **Level 4:** Granular topics or niche areas within each Level 3 division (e.g., Data Validation, 3D Printing, Oral Hygiene Techniques, etc.)
- **Level 5:** Specialized subtopics or emerging areas within Level 4.
- **Level 6:** Micro-level details (specific techniques, terminologies, procedures, or methodologies) within Level 5.
- **Level 7:** Further refinement of Level 6 topics into distinct processes or methods.
- **Level 8:** Subdivisions capturing experimental techniques, applications, or anatomical details derived from Level 7.
- **Level 9:** Specific examples such as studies, materials, or tools illustrating Level 8 topics.
- **Level 10:** Intricate specifics like precise protocols, algorithms, or case study details built on Level 9.
- **Level 11:** Further micro-detailed refinements of Level 10 elements.
- **Level 12:** Subdivisions that focus on minute operational dynamics or validation techniques.
- **Level 13:** Detailed breakdowns into statistical or methodological variants.
- **Level 14:** Fine-grained adjustments and optimization processes.
- **Level 15:** The most intricate, minute details such as precise parameters, exact measurements, or real-world application specifics.

**Instructions:**
1. **Extract Terms:**
   Thoroughly analyze the input data to extract as many detailed dental-specific terms as possible. Include procedures, technologies, treatment methods, research methodologies, emerging trends, anatomical structures, and any other highly specific aspects of dentistry.

2. **Assign to Categories:**
   Map each extracted term uniquely to one of the three primary categories: **Dental Informatics**, **Digital Dentistry**, and **Dental Healthcare**.

3. **Build a Fifteen-Level Deep Hierarchy:**
   - **Level 1 (Main Categories):** Use the three primary branches.
   - **Level 2 (Subcategories):** Organize related terms into broad groups (please include as many broad groups as possible for each main category!! Please give at least 4 broad groups for each main categories).
   - **Level 3 (Divisions):** Break down the subcategories into more specific clusters.
   - **Level 4 (Niche Topics):** Drill down into detailed niche topics within each Level 3 division.
   - **Level 5 (Specialized Subtopics):** Identify emerging areas or specialized clusters within Level 4.
   - **Level 6 (Micro-Level Details):** Include concrete techniques, terminologies, or methodologies specific to a subtopic.
   - **Level 7 (Refined Processes):** Further refine micro-level details into distinct processes or methods.
   - **Level 8 (Experimental/Subprocesses):** Subdivide Level 7 into experimental techniques, validation methods, or anatomical details.
   - **Level 9 (Case Examples/Materials):** Identify specific studies, materials, tools, or illustrative examples that embody Level 8 topics.
   - **Level 10 (Intricate Specifics):** Capture precise protocols, algorithms, or examples that give detailed context to Level 9.
   - **Level 11:** Further detail the Level 10 elements with additional micro-level refinements.
   - **Level 12:** Break down Level 11 elements into minute operational or validation dynamics.
   - **Level 13:** Elaborate on statistical or methodological variations within Level 12.
   - **Level 14:** Provide fine-tuning details related to optimization or adjustments.
   - **Level 15:** Conclude with the most detailed, real-world specific items such as exact parameters, precise metrics, or specific case applications.

4. **Output Requirements:**
   - Present the taxonomy as a nested JSON object.
   - Use keys such as "label" for names, "subcategories" for nested groupings, and "terms" for the most granular items.
   - Ensure the hierarchy is logically structured with at least fifteen levels deep.

---

**INPUT DATA:**

- **SUBTOPICS:**
{subtopics}

- **TITLES:**
{titles}

- **ABSTRACTS:**
{abstracts}

- **KEYWORDS:**
{keywords}

---

**OUTPUT FORMAT EXAMPLE (Fifteen Levels Deep):**

```json
{{
  "Dentistry": {{
    "Dental Informatics": {{
      "label": "Dental Informatics",
      "subcategories": {{
        "Electronic Health Records": {{
          "label": "Electronic Health Records",
          "subcategories": {{
            "Data Management": {{
              "label": "Data Management",
              "subcategories": {{
                "Data Validation": {{
                  "label": "Data Validation",
                  "subcategories": {{
                    "Real-Time Processes": {{
                      "label": "Real-Time Processes",
                      "subcategories": {{
                        "Live Data Entry": {{
                          "label": "Live Data Entry",
                          "subcategories": {{
                            "Validation Algorithms": {{
                              "label": "Validation Algorithms",
                              "subcategories": {{
                                "Error Detection": {{
                                  "label": "Error Detection",
                                  "subcategories": {{
                                    "Statistical Models": {{
                                      "label": "Statistical Models",
                                      "subcategories": {{
                                        "Regression Analysis": {{
                                          "label": "Regression Analysis",
                                          "subcategories": {{
                                            "Probabilistic Inference": {{
                                              "label": "Probabilistic Inference",
                                              "subcategories": {{
                                                "Bayesian Methods": {{
                                                  "label": "Bayesian Methods",
                                                  "subcategories": {{
                                                    "Markov Chain Monte Carlo": {{
                                                      "label": "Markov Chain Monte Carlo",
                                                      "subcategories": {{
                                                        "Gibbs Sampling": {{
                                                          "label": "Gibbs Sampling",
                                                          "terms": [
                                                            {{ "label": "Convergence Criteria" }},
                                                            {{ "label": "Chain Mixing Efficiency" }}
                                                          ]
                                                        }}
                                                      }}
                                                    }}
                                                  }}
                                                }}
                                              }}
                                            }}
                                          }}
                                        }}
                                      }}
                                    }}
                                  }}
                                }}
                              }}
                            }}
                          }}
                        }}
                      }}
                    }}
                  }}
                }}
              }}
            }}
          }}
        }}
      }}
    }},
    "Digital Dentistry": {{
      "label": "Digital Dentistry",
      "subcategories": {{
        "3D Technologies": {{
          "label": "3D Technologies",
          "subcategories": {{
            "3D Printing": {{
              "label": "3D Printing",
              "subcategories": {{
                "Prosthetics Fabrication": {{
                  "label": "Prosthetics Fabrication",
                  "subcategories": {{
                    "Advanced Materials": {{
                      "label": "Advanced Materials",
                      "subcategories": {{
                        "Composite Materials": {{
                          "label": "Composite Materials",
                          "subcategories": {{
                            "Material Testing": {{
                              "label": "Material Testing",
                              "subcategories": {{
                                "Stress Analysis": {{
                                  "label": "Stress Analysis",
                                  "subcategories": {{
                                    "Finite Element Analysis": {{
                                      "label": "Finite Element Analysis",
                                      "subcategories": {{
                                        "Mesh Generation": {{
                                          "label": "Mesh Generation",
                                          "subcategories": {{
                                            "Load Distribution": {{
                                              "label": "Load Distribution",
                                              "subcategories": {{
                                                "Optimization Algorithms": {{
                                                  "label": "Optimization Algorithms",
                                                  "subcategories": {{
                                                    "Genetic Algorithms": {{
                                                      "label": "Genetic Algorithms",
                                                      "terms": [
                                                        {{ "label": "Crossover Techniques" }},
                                                        {{ "label": "Mutation Strategies" }}
                                                      ]
                                                    }}
                                                  }}
                                                }}
                                              }}
                                            }}
                                          }}
                                        }}
                                      }}
                                    }}
                                  }}
                                }}
                              }}
                            }}
                          }}
                        }}
                      }}
                    }}
                  }}
                }}
              }}
            }}
          }}
        }}
      }}
    }},
    "Dental Healthcare": {{
      "label": "Dental Healthcare",
      "subcategories": {{
        "Preventive Dentistry": {{
          "label": "Preventive Dentistry",
          "subcategories": {{
            "Oral Hygiene Techniques": {{
              "label": "Oral Hygiene Techniques",
              "subcategories": {{
                "Fluoride Therapies": {{
                  "label": "Fluoride Therapies",
                  "subcategories": {{
                    "Application Methods": {{
                      "label": "Application Methods",
                      "subcategories": {{
                        "Dosage Optimization": {{
                          "label": "Dosage Optimization",
                          "subcategories": {{
                            "Delivery Systems": {{
                              "label": "Delivery Systems",
                              "subcategories": {{
                                "Custom Trays": {{
                                  "label": "Custom Trays",
                                  "subcategories": {{
                                    "Precision Fit": {{
                                      "label": "Precision Fit",
                                      "subcategories": {{
                                        "Sustained Release": {{
                                          "label": "Sustained Release",
                                          "subcategories": {{
                                            "Timed Release Polymers": {{
                                              "label": "Timed Release Polymers",
                                              "terms": [
                                                {{ "label": "Polymer Degradation Rates" }},
                                                {{ "label": "Controlled Flow Systems" }}
                                              ]
                                            }}
                                          }}
                                        }}
                                      }}
                                    }}
                                  }}
                                }}
                              }}
                            }}
                          }}
                        }}
                      }}
                    }}
                  }}
                }}
              }}
            }}
          }}
        }}
      }}
    }}
  }}
}}
"""

from langchain.llms import HuggingFaceHub
import os
import pandas as pd

def limit_text(text, max_chars):
    return text[:max_chars]

def create_taxonomy(subtopics_text: str, titles_text: str, abstracts_text: str, keywords_text: str) -> str:
    openai_api_key = os.getenv('OPENAI_API_KEY')
    llm = ChatOpenAI(model='gpt-4o', temperature=0.1, max_tokens=15000, openai_api_key=openai_api_key)

    prompt = PromptTemplate(template=taxonomy_prompt, input_variables=["subtopics", "titles", "abstracts", "keywords"])

    taxonomy_chain = LLMChain(llm=llm, prompt=prompt)

    result = taxonomy_chain.predict(
        subtopics=subtopics_text,
        titles=titles_text,
        abstracts=abstracts_text,
        keywords=keywords_text
    )

    return result

# Collect all titles, abstracts, and keywords
titles_text = '\n'.join(df['Title'].dropna().tolist())
abstracts_text = '\n'.join(df['Abstract'].dropna().tolist())
keywords_text = '\n'.join(df['keywords from documents supplied by authors'].dropna().tolist())

# Limit the input sizes to avoid exceeding token limits
max_chars = 30000  # Adjust as needed
titles_text = limit_text(titles_text, max_chars)
abstracts_text = limit_text(abstracts_text, max_chars)
keywords_text = limit_text(keywords_text, max_chars)

# Generate the taxonomy
taxonomy_text = create_taxonomy(subtopics_text, titles_text, abstracts_text, keywords_text)


# Print and save the final taxonomy
print("Final Taxonomy:\n", taxonomy_text)

with open('taxonomy.txt', 'w') as file:
    file.write(taxonomy_text)

df

!pip install plotly

import json

with open('/content/taxonomy.txt', 'r') as f:
    file_content = f.read().strip()

# Check if the file contains a markdown code block with JSON.
if "```json" in file_content:
    # Extract the substring starting from the first '{' and ending at the last '}'
    json_start = file_content.find('{')
    json_end = file_content.rfind('}')
    if json_start == -1 or json_end == -1 or json_start > json_end:
        raise ValueError("Could not find valid JSON content in the file.")
    json_text = file_content[json_start:json_end+1]
else:
    # If no markdown code block marker is found, try to identify JSON boundaries.
    json_start = file_content.find('{')
    json_end = file_content.rfind('}')
    if json_start != -1 and json_end != -1 and json_start < json_end:
        json_text = file_content[json_start:json_end+1]
    else:
        json_text = file_content  # assuming the file is pure JSON

# Now try loading the JSON.
try:
    taxonomy_data = json.loads(json_text)
    print(taxonomy_data)
except json.JSONDecodeError as e:
    print("JSON decoding error:", e)
    # Optionally, print the extracted json_text for debugging
    print("Extracted JSON text:")
    print(json_text)

def extract_paths(data, parent_label='', paths=None, node_type='category'):
    if paths is None:
        paths = []
    current_label = parent_label
    if isinstance(data, dict):
        for key, value in data.items():
            if key == 'label':
                current_label = value
                paths.append({'parent': parent_label, 'label': current_label, 'terms': node_type})
            elif key == 'terms':
                for term in value:
                    term_label = term.get('label', '')
                    if term_label:
                        paths.append({'parent': current_label, 'label': term_label, 'terms': term_label})
            elif key == 'subcategories':
                for subcat in value.values():
                    extract_paths(subcat, current_label, paths, node_type='subcategory')
            else:
                extract_paths(value, current_label, paths, node_type=node_type)
    elif isinstance(data, list):
        for item in data:
            extract_paths(item, parent_label, paths, node_type=node_type)
    else:
        pass
    return paths

# Extract the paths
paths = extract_paths(taxonomy_data)

paths

import pandas as pd

# Create the DataFrame
visual_df = pd.DataFrame(paths)

# Check the columns of the DataFrame
print("Columns in visual_df:", visual_df.columns)

# Preview the DataFrame
print("First few rows of visual_df:")
print(visual_df.head())

# Print the first few entries in paths
print("First few entries in paths:")
print(paths[:5])

# Remove any entries with empty labels
visual_df = visual_df[visual_df['label'] != '']

# Reset index for cleanliness
visual_df.reset_index(drop=True, inplace=True)

visual_df

visual_df['parent'] = visual_df['parent'].replace("", None)
print(visual_df.head())

!pip install --upgrade plotly

import plotly.express as px

# Create the sunburst chart
fig = px.sunburst(
    visual_df,
    names='label',
    parents='parent',
    title='Interactive Dental Taxonomy',
    maxdepth=25
)

# Update layout for better visualization
fig.update_layout(
    margin=dict(t=50, l=25, r=25, b=25)
)

# Show the figure
fig.write_html("sunburst_chart.html")
fig.show()

fig = px.treemap(
    visual_df,
    names='label',
    parents='parent',
    title='Interactive Dental Taxonomy Treemap',
    maxdepth=25
)

fig.update_layout(
    margin=dict(t=50, l=25, r=25, b=25)
)

fig.write_html("treemap_chart.html")
fig.show()

!pip install pyvis

from pyvis.network import Network

# Initialize the network
net = Network(height='750px', width='100%', bgcolor='#FFFFFF', font_color='black', notebook=True, cdn_resources='remote')

# Add nodes and edges
nodes = set()
for index, row in visual_df.iterrows():
    net.add_node(row['label'], label=row['label'])
    nodes.add(row['label'])
    if row['parent'] and row['parent'] != '':
        net.add_node(row['parent'], label=row['parent'])
        net.add_edge(row['parent'], row['label'])

# Enable physics for better layout
net.set_options('''
var options = {
  "physics": {
    "enabled": true,
    "stabilization": {
      "enabled": true,
      "iterations": 1000,
      "updateInterval": 25
    },
    "barnesHut": {
      "gravitationalConstant": -8000,
      "centralGravity": 0.3,
      "springLength": 95,
      "springConstant": 0.04,
      "damping": 0.09,
      "avoidOverlap": 0
    }
  }
}
''')

# Generate and display the network graph
net.show('taxonomy_network.html')

!pip install dash

!pip install jupyter_dash -q
!pip install dash
from jupyter_dash import JupyterDash
import dash
from dash import dcc, html
from dash.dependencies import Input, Output, State

app = JupyterDash(__name__)  # Use JupyterDash

app.layout = html.Div([
    dcc.Input(id='search-term', type='text', placeholder='Search...'),
    dcc.Graph(id='taxonomy-graph')
])

@app.callback(
    Output('taxonomy-graph', 'figure'),
    Input('search-term', 'value')
)
def update_figure(search_term):
    filtered_df = visual_df[visual_df['label'].str.contains(search_term, case=False, na=False)] if search_term else visual_df
    fig = px.sunburst(
        filtered_df,
        names='label',
        parents='parent',
        hover_data=['label'],
        title='Interactive Dental Taxonomy'
    )
    fig.update_layout(margin=dict(t=50, l=25, r=25, b=25))
    return fig

if __name__ == '__main__':
    app.run_server(mode='inline', debug=True)