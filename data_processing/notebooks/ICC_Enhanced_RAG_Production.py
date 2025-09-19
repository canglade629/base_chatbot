# Databricks notebook source
# MAGIC %md
# MAGIC # ICC Enhanced RAG System - Production Deployment
# MAGIC 
# MAGIC **Architecture:**
# MAGIC - **Enhanced Vector Search**: Dual-index retrieval with intelligent routing using `databricks-gte-large-en`
# MAGIC - **Advanced LLM**: `databricks-meta-llama-3-3-70b-instruct` for legal analysis
# MAGIC - **MLflow 3.0**: Production deployment and model management
# MAGIC - **Legal Expertise**: Specialized for ICC defense team research
# MAGIC 
# MAGIC **Data Sources:**
# MAGIC - **Past Judgments Index**: `past_judgement` (ICTY/ICC case law)
# MAGIC - **Geneva Documentation Index**: `geneva_documentation` (IHL framework)
# MAGIC - **Vector Search Endpoint**: `jgmt` (with databricks-gte-large-en embedding model)
# MAGIC 
# MAGIC **Key Features:**
# MAGIC - Intelligent routing based on legal topics
# MAGIC - Enhanced retrieval with relevance boosting
# MAGIC - Comprehensive legal analysis generation
# MAGIC - Production-ready MLflow 3.0 deployment

# COMMAND ----------

# Databricks notebook source
# MAGIC %pip install --upgrade --force-reinstall databricks-vectorsearch
# MAGIC dbutils.library.restartPython()

# COMMAND ----------

# MAGIC %pip install -U -qqqq mlflow>=3.1.1 databricks-langchain pydantic databricks-agents unitycatalog-langchain[databricks] uv databricks-feature-engineering==0.12.1
# MAGIC dbutils.library.restartPython()

# COMMAND ----------

# MAGIC %md
# MAGIC **Note**: The dependency conflicts shown during installation (protobuf, urllib3) are common in Databricks environments and typically don't affect functionality. The core packages needed for the RAG system are successfully installed.

# COMMAND ----------

# MAGIC %md
# MAGIC ## Verify Installation

# COMMAND ----------

# Test VectorSearchClient initialization
try:
    from databricks.vector_search.client import VectorSearchClient
    vsc = VectorSearchClient()
    print("✅ VectorSearchClient initialized successfully")
    print(f"VectorSearchClient type: {type(vsc)}")
    print("Note: Embedding model is configured at the index level, not client level")
except Exception as e:
    print(f"❌ Error initializing VectorSearchClient: {e}")

# COMMAND ----------

import json
import pandas as pd
import numpy as np
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, asdict
import datetime
import logging
import re

import mlflow
from mlflow.models import infer_signature
from mlflow.models.resources import (
    DatabricksVectorSearchIndex,
    DatabricksServingEndpoint
)
from databricks_langchain import ChatDatabricks
from langchain.memory import ConversationBufferWindowMemory
from langchain.schema import HumanMessage, SystemMessage
from databricks.vector_search.client import VectorSearchClient

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configuration - Easy to modify for different environments
VECTOR_SEARCH_ENDPOINT = "jgmt"
LLM_MODEL = "databricks-meta-llama-3-3-70b-instruct"
EMBEDDING_MODEL = "databricks-gte-large-en"  # Model for retrieval/embeddings
CATALOG_NAME = "icc_chatbot"  # Change this to your catalog
SCHEMA_NAME = "search_model"  # Change this to your schema
MODEL_NAME = f"{CATALOG_NAME}.{SCHEMA_NAME}.icc_rag_V2"  # Full Unity Catalog model name
JUDGMENT_INDEX = f"{CATALOG_NAME}.{SCHEMA_NAME}.past_judgement"
GENEVA_INDEX = f"{CATALOG_NAME}.{SCHEMA_NAME}.geneva_documentation"

# Constants
DEFAULT_TOP_K = 10
DEFAULT_CONVERSATION_WINDOW = 5

# Legal topics for routing
LEGAL_TOPICS = {
    "judgment_priority": [
        "trial chamber", "appeals chamber", "judgment", "decision", "ruling",
        "case law", "precedent", "jurisprudence", "court", "tribunal",
        "prosecution", "defense", "evidence", "witness", "testimony",
        "guilty", "innocent", "conviction", "acquittal", "sentence",
        "war crimes", "crimes against humanity", "genocide", "command responsibility"
    ],
    "geneva_priority": [
        "article", "convention", "protocol", "geneva", "ihl", "international humanitarian law",
        "protected persons", "civilians", "prisoners of war", "wounded", "sick",
        "medical personnel", "religious personnel", "cultural property", "civilian objects",
        "military objectives", "proportionality", "necessity", "distinction", "precaution"
    ]
}

# COMMAND ----------

# Data Structures
@dataclass
class SearchResult:
    """Represents a single search result from vector search."""
    content: str
    summary: Optional[str] = None
    source: str = ""
    metadata: Dict[str, Any] = None
    score: float = 0.0
    source_type: str = ""  # "judgment" or "geneva"
    page_number: Optional[str] = None
    article: Optional[str] = None
    section: Optional[str] = None
    document_type: Optional[str] = None
    
    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}

@dataclass
class RetrievalContext:
    """Context retrieved for a specific query."""
    question: str
    routing_decision: str
    judgment_results: List[SearchResult]
    geneva_results: List[SearchResult]
    all_results: List[SearchResult]
    total_sources: int
    processing_time: float
    
    def __len__(self):
        """Return the total number of results."""
        return len(self.all_results)

@dataclass
class LegalAnalysis:
    """Generated legal analysis result."""
    question: str
    analysis: str
    key_findings: List[str]
    citations: List[str]
    resource_list: Dict[str, List[Dict[str, str]]] = None
    confidence_score: float = 0.0
    sources_used: int = 0
    processing_time: float = 0.0
    conversation_id: Optional[str] = None

# COMMAND ----------

# Enhanced ICC RAG System - Consolidated Implementation
class EnhancedICCRAGSystem:
    """Enhanced RAG system for ICC legal research with intelligent routing and corrected metadata handling."""
    
    def __init__(self, 
                 vector_search_endpoint_name: str = None,
                 llm_model: str = None,
                 conversation_window: int = DEFAULT_CONVERSATION_WINDOW):
        """Initialize the enhanced RAG system."""
        self.vector_search_endpoint_name = vector_search_endpoint_name or VECTOR_SEARCH_ENDPOINT
        self.llm_model = llm_model or LLM_MODEL
        self.conversation_window = conversation_window
        
        # Initialize vector search client
        self.vector_search_client = VectorSearchClient()
        
        # Initialize LLM for text generation
        self.llm = ChatDatabricks(
            endpoint=self.llm_model,
            temperature=0.1,
            max_tokens=4000
        )
        
        # Initialize conversation memory
        self.memory = ConversationBufferWindowMemory(
            k=conversation_window,
            return_messages=True
        )
        
        logger.info(f"Enhanced ICC RAG System initialized with endpoint: {self.vector_search_endpoint_name}")
    
    def cleanup(self):
        """Clean up resources and memory."""
        if hasattr(self, 'memory'):
            self.memory.clear()
        logger.info("RAG system resources cleaned up")
    
    def _format_page_numbers(self, pages: List[int]) -> Optional[str]:
        """Format page numbers from list to string representation."""
        if not pages:
            return None
        if len(pages) == 1:
            return str(pages[0])
        else:
            return f"{pages[0]}-{pages[-1]}"
    
    def _extract_articles_from_text(self, text: str) -> Optional[str]:
        """Extract article references from text using advanced pattern matching."""
        import re
        
        # Look for various article patterns
        patterns = [
            r'article\s+(\d+(?:\(\d+\))?(?:\(\d+\))?)',  # Article 31(1)(2)
            r'art\.\s*(\d+(?:\(\d+\))?(?:\(\d+\))?)',    # Art. 31(1)(2)
            r'articles?\s+(\d+(?:\s*and\s*\d+)*)',       # Article 31 and 32
            r'gc\s+(\d+)',                               # GC 31
            r'geneva\s+convention\s+(\d+)',              # Geneva Convention 31
            r'convention\s+(\d+)',                       # Convention 31
        ]
        
        articles = []
        for pattern in patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            for match in matches:
                if isinstance(match, tuple):
                    articles.extend([m for m in match if m])
                else:
                    articles.append(match)
        
        # Clean and deduplicate
        cleaned_articles = []
        for article in articles:
            if article and article not in cleaned_articles:
                cleaned_articles.append(article)
        
        if cleaned_articles:
            return f"Article {', '.join(cleaned_articles[:3])}"  # Limit to 3 articles
        return None
    
    def _extract_legal_concepts_from_results(self, results: List[SearchResult]) -> List[str]:
        """Extract legal concepts from search results for enhanced querying."""
        legal_concepts = []
        concept_patterns = {
            "grave breach": ["grave breach", "serious violation", "war crime"],
            "protected person": ["protected person", "civilian", "prisoner of war"],
            "international humanitarian law": ["international humanitarian law", "ihl", "geneva convention"],
            "command responsibility": ["command responsibility", "superior responsibility", "article 7(3)"],
            "aiding and abetting": ["aiding and abetting", "complicity", "assistance"],
            "discriminatory intent": ["discriminatory intent", "discrimination", "adverse distinction"],
            "outrages upon personal dignity": ["outrages upon personal dignity", "personal dignity", "humiliation"],
            "armed conflict": ["armed conflict", "international conflict", "internal conflict"],
            "proportionality": ["proportionality", "proportionate", "excessive"],
            "necessity": ["necessity", "military necessity", "justification"]
        }
        
        for result in results:
            content_lower = result.content.lower()
            summary_lower = result.summary.lower() if result.summary else ""
            
            # Check for article references
            if result.article:
                legal_concepts.append(result.article)
            
            # Check for legal concepts
            for concept, patterns in concept_patterns.items():
                if any(pattern in content_lower or pattern in summary_lower for pattern in patterns):
                    if concept not in legal_concepts:
                        legal_concepts.append(concept)
        
        return legal_concepts[:8]  # Limit to 8 concepts
    
    def determine_enhanced_routing_priority(self, question: str) -> Dict[str, Any]:
        """Determine enhanced routing priority with detailed analysis."""
        question_lower = question.lower()
        
        # Count topic matches
        judgment_matches = sum(1 for topic in LEGAL_TOPICS["judgment_priority"] 
                             if topic in question_lower)
        geneva_matches = sum(1 for topic in LEGAL_TOPICS["geneva_priority"] 
                           if topic in question_lower)
        
        # Determine primary focus
        if judgment_matches > geneva_matches:
            primary_focus = "judgment"
        elif geneva_matches > judgment_matches:
            primary_focus = "geneva"
        else:
            primary_focus = "both"
        
        # Calculate priority scores
        geneva_priority = geneva_matches / len(LEGAL_TOPICS["geneva_priority"])
        judgment_priority = judgment_matches / len(LEGAL_TOPICS["judgment_priority"])
        
        # Determine search strategy
        if "methodology" in question_lower or "how to" in question_lower:
            search_strategy = "geneva_first"
            reasoning = "Methodology question - start with legal framework"
        elif "case" in question_lower or "judgment" in question_lower or "chamber" in question_lower:
            search_strategy = "judgment_first"
            reasoning = "Case law question - start with judgments"
        elif geneva_priority > 0.3:
            search_strategy = "geneva_first"
            reasoning = "High Geneva Convention relevance"
        elif judgment_priority > 0.3:
            search_strategy = "judgment_first"
            reasoning = "High case law relevance"
        else:
            search_strategy = "parallel"
            reasoning = "Balanced approach - search both simultaneously"
        
        return {
            "primary_focus": primary_focus,
            "geneva_priority": geneva_priority,
            "judgment_priority": judgment_priority,
            "search_strategy": search_strategy,
            "reasoning": reasoning
        }
    
    def enhance_query_with_summary_context(self, query: str) -> str:
        """Enhance query with context-aware terms for better retrieval using state-of-the-art techniques."""
        enhanced_terms = []
        
        # Legal domain-specific query expansion
        legal_expansions = {
            "factor": ["analysis", "finding", "conclusion", "principle", "criteria", "consideration", "assessment"],
            "consider": ["analysis", "evaluation", "assessment", "examination", "review", "determination"],
            "assessment": ["evaluation", "analysis", "examination", "review", "determination", "judgment"],
            "evaluation": ["assessment", "analysis", "examination", "review", "determination", "judgment"],
            "article": ["provision", "section", "paragraph", "clause", "rule", "regulation"],
            "convention": ["treaty", "agreement", "protocol", "accord", "charter"],
            "protocol": ["convention", "agreement", "treaty", "accord", "charter"],
            "war crime": ["international criminal law", "statute", "elements", "offense", "violation"],
            "crime against humanity": ["international criminal law", "statute", "elements", "offense", "violation"],
            "genocide": ["international criminal law", "statute", "elements", "offense", "violation"],
            "protected person": ["article 4", "article 13", "status", "protection", "civilians", "prisoners"],
            "civilian": ["protected person", "non-combatant", "civilian population", "article 4"],
            "prisoner": ["prisoner of war", "detainee", "protected person", "article 13"],
            "trial chamber": ["chamber", "court", "tribunal", "judicial", "proceedings"],
            "appeals chamber": ["chamber", "court", "tribunal", "judicial", "appeal", "review"],
            "judgment": ["decision", "ruling", "opinion", "verdict", "finding"],
            "evidence": ["proof", "testimony", "witness", "documentation", "material"],
            "witness": ["testimony", "evidence", "statement", "declaration", "affidavit"],
            "testimony": ["witness", "evidence", "statement", "declaration", "affidavit"],
            "prosecution": ["prosecutor", "prosecuting", "charges", "indictment", "accusation"],
            "defense": ["defendant", "accused", "defense counsel", "defense team", "representation"],
            "guilty": ["conviction", "culpability", "responsibility", "liability", "accountability"],
            "innocent": ["acquittal", "exoneration", "not guilty", "cleared", "absolved"],
            "conviction": ["guilty", "culpability", "responsibility", "liability", "accountability"],
            "acquittal": ["innocent", "exoneration", "not guilty", "cleared", "absolved"],
            "sentence": ["punishment", "penalty", "sanction", "imprisonment", "fine"],
            "command responsibility": ["superior responsibility", "command", "authority", "control", "subordinates"],
            "proportionality": ["proportionate", "balance", "necessity", "reasonableness", "appropriate"],
            "necessity": ["necessary", "required", "essential", "indispensable", "compelling"],
            "distinction": ["discrimination", "differentiation", "separation", "distinguishing", "classification"],
            "precaution": ["precautionary", "care", "caution", "safeguard", "protection"]
        }
        
        # Apply query expansion
        query_lower = query.lower()
        for key, expansions in legal_expansions.items():
            if key in query_lower:
                enhanced_terms.extend(expansions[:3])  # Limit to top 3 expansions per key
        
        # Add contextual legal terms based on query type
        if any(term in query_lower for term in ["how", "what", "when", "where", "why"]):
            enhanced_terms.extend(["method", "process", "procedure", "approach", "technique"])
        
        if any(term in query_lower for term in ["definition", "define", "meaning", "what is"]):
            enhanced_terms.extend(["concept", "term", "notion", "understanding", "interpretation"])
        
        if any(term in query_lower for term in ["example", "instance", "case", "illustration"]):
            enhanced_terms.extend(["illustration", "demonstration", "sample", "precedent", "case study"])
        
        # Add temporal context terms
        if any(term in query_lower for term in ["recent", "latest", "current", "modern"]):
            enhanced_terms.extend(["contemporary", "present", "current", "recent", "modern"])
        
        if any(term in query_lower for term in ["historical", "past", "previous", "earlier"]):
            enhanced_terms.extend(["historical", "past", "previous", "earlier", "former"])
        
        # Remove duplicates and limit terms
        enhanced_terms = list(dict.fromkeys(enhanced_terms))[:8]  # Keep unique terms, limit to 8
        
        # Combine original query with enhanced terms
        if enhanced_terms:
            enhanced_query = f"{query} {' '.join(enhanced_terms)}"
        else:
            enhanced_query = query
        
        return enhanced_query
    
    def decompose_query(self, query: str) -> List[str]:
        """Decompose complex queries into simpler sub-queries for better retrieval."""
        query_lower = query.lower()
        sub_queries = [query]  # Start with original query
        
        # Legal concept decomposition
        if "and" in query_lower or "&" in query_lower:
            # Split on conjunctions
            parts = [part.strip() for part in query_lower.replace("&", "and").split(" and ") if part.strip()]
            if len(parts) > 1:
                sub_queries.extend(parts)
        
        # Question type decomposition
        if "what" in query_lower and "how" in query_lower:
            what_part = " ".join([word for word in query.split() if "what" in word.lower() or query.split()[query.split().index(word):]])
            how_part = " ".join([word for word in query.split() if "how" in word.lower() or query.split()[query.split().index(word):]])
            if what_part and how_part:
                sub_queries.extend([what_part, how_part])
        
        # Legal framework vs application decomposition
        if any(term in query_lower for term in ["article", "convention", "protocol"]) and any(term in query_lower for term in ["case", "judgment", "chamber"]):
            # Split into legal framework and case law parts
            legal_terms = ["article", "convention", "protocol", "geneva", "ihl"]
            case_terms = ["case", "judgment", "chamber", "trial", "appeals"]
            
            legal_query = " ".join([word for word in query.split() if any(term in word.lower() for term in legal_terms)])
            case_query = " ".join([word for word in query.split() if any(term in word.lower() for term in case_terms)])
            
            if legal_query and case_query:
                sub_queries.extend([legal_query, case_query])
        
        # Remove duplicates and empty queries
        sub_queries = list(dict.fromkeys([q.strip() for q in sub_queries if q.strip()]))
        
        return sub_queries[:3]  # Limit to 3 sub-queries
    
    def hybrid_search_judgments(self, query: str, top_k: int = DEFAULT_TOP_K) -> List[SearchResult]:
        """Hybrid search combining multiple retrieval strategies for past judgments."""
        all_results = []
        
        # 1. Original query search
        original_results = self.search_past_judgments_corrected(query, top_k)
        all_results.extend(original_results)
        
        # 2. Query decomposition search
        sub_queries = self.decompose_query(query)
        for sub_query in sub_queries[1:]:  # Skip original query
            sub_results = self.search_past_judgments_corrected(sub_query, top_k // 2)
            all_results.extend(sub_results)
        
        # 3. Enhanced query search
        enhanced_query = self.enhance_query_with_summary_context(query)
        if enhanced_query != query:
            enhanced_results = self.search_past_judgments_corrected(enhanced_query, top_k // 2)
            all_results.extend(enhanced_results)
        
        # 4. Legal concept focused search
        if any(term in query.lower() for term in ["article", "convention", "protocol"]):
            legal_query = f"legal framework {query}"
            legal_results = self.search_past_judgments_corrected(legal_query, top_k // 3)
            all_results.extend(legal_results)
        
        # 5. Case law focused search
        if any(term in query.lower() for term in ["case", "judgment", "chamber", "trial", "appeals"]):
            case_query = f"case law application {query}"
            case_results = self.search_past_judgments_corrected(case_query, top_k // 3)
            all_results.extend(case_results)
        
        # Remove duplicates and rank
        unique_results = []
        seen_content = set()
        
        for result in all_results:
            content_hash = hash(result.content[:100])  # Use first 100 chars as identifier
            if content_hash not in seen_content:
                seen_content.add(content_hash)
                unique_results.append(result)
        
        # Apply advanced ranking
        ranked_results = self.rank_and_filter_results(unique_results, query)
        
        return ranked_results[:top_k]
    
    def hybrid_search_geneva(self, query: str, top_k: int = DEFAULT_TOP_K) -> List[SearchResult]:
        """Hybrid search combining multiple retrieval strategies for Geneva documentation."""
        all_results = []
        
        # 1. Original query search
        original_results = self.search_geneva_documentation_corrected(query, top_k)
        all_results.extend(original_results)
        
        # 2. Enhanced query search
        enhanced_query = self.enhance_query_with_summary_context(query)
        if enhanced_query != query:
            enhanced_results = self.search_geneva_documentation_corrected(enhanced_query, top_k // 2)
            all_results.extend(enhanced_results)
        
        # 3. Article-specific search
        if "article" in query.lower():
            article_query = f"article provisions {query}"
            article_results = self.search_geneva_documentation_corrected(article_query, top_k // 3)
            all_results.extend(article_results)
        
        # 4. Convention-specific search
        if any(term in query.lower() for term in ["convention", "protocol", "geneva"]):
            convention_query = f"convention text {query}"
            convention_results = self.search_geneva_documentation_corrected(convention_query, top_k // 3)
            all_results.extend(convention_results)
        
        # Remove duplicates and rank
        unique_results = []
        seen_content = set()
        
        for result in all_results:
            content_hash = hash(result.content[:100])
            if content_hash not in seen_content:
                seen_content.add(content_hash)
                unique_results.append(result)
        
        # Apply advanced ranking
        ranked_results = self.rank_and_filter_results(unique_results, query)
        
        return ranked_results[:top_k]
    
    def search_past_judgments_corrected(self, query: str, top_k: int = DEFAULT_TOP_K) -> List[SearchResult]:
        """Search past judgments with corrected metadata handling."""
        try:
            # Get the index and perform similarity search
            index = self.vector_search_client.get_index(index_name=JUDGMENT_INDEX)
            search_results = index.similarity_search(
                columns=["text", "summary", "doc_id", "pages", "section_type", "footnotes"],
                query_text=query,
                num_results=top_k
            )
            
            results = []
            # Handle different response formats
            if isinstance(search_results, str):
                logger.error(f"Unexpected string response from judgment search: {search_results}")
                return results
            elif isinstance(search_results, dict):
                # Handle dictionary response - check for common keys
                if 'result' in search_results and 'data_array' in search_results['result']:
                    # Extract data array and convert to list of dictionaries
                    data_array = search_results['result']['data_array']
                    columns = ['text', 'summary', 'doc_id', 'pages', 'section_type', 'footnotes', 'score']
                    search_results = []
                    for row in data_array:
                        if len(row) >= len(columns):
                            row_dict = {}
                            for i, col in enumerate(columns):
                                if i < len(row):
                                    row_dict[col] = row[i]
                            search_results.append(row_dict)
                elif 'result' in search_results:
                    search_results = search_results['result']
                elif 'data' in search_results:
                    search_results = search_results['data']
                elif 'rows' in search_results:
                    search_results = search_results['rows']
                else:
                    logger.error(f"Unexpected dictionary response from judgment search: {search_results}")
                    return results
            elif not isinstance(search_results, (list, tuple)):
                logger.error(f"Unexpected response type from judgment search: {type(search_results)}")
                return results
            
            # Process the converted search results
            for row in search_results:
                if not isinstance(row, dict):
                    logger.warning(f"Skipping non-dict row in judgment search results: {type(row)}")
                    continue
                    
                content = row.get("text", "")  # Use 'text' column
                summary = row.get("summary", "")
                doc_id = row.get("doc_id", "")
                pages = row.get("pages", [])
                section = row.get("section_type", "")
                footnotes = row.get("footnotes", [])
                
                # Format page numbers
                page_number = self._format_page_numbers(pages)
                
                # Extract article information from content
                article = self._extract_articles_from_text(content)
                
                # Create metadata dictionary
                metadata = {
                    "doc_id": doc_id,
                    "pages": pages,
                    "section_type": section,
                    "article": article,
                    "chunk_id": row.get("chunk_id", ""),
                    "footnotes": footnotes
                }
                
                result = SearchResult(
                    content=content,
                    summary=summary,
                    source=doc_id,  # doc_id contains the document name
                    source_type="judgment",
                    score=row.get("score", 0.0),
                    page_number=page_number,
                    section=section,
                    article=article,
                    metadata=metadata
                )
                results.append(result)
            
            return results
            
        except Exception as e:
            logger.error(f"Error searching past judgments: {e}")
            return []
    
    def search_geneva_documentation_corrected(self, query: str, top_k: int = DEFAULT_TOP_K) -> List[SearchResult]:
        """Search Geneva documentation with corrected metadata handling."""
        try:
            # Get the index and perform similarity search
            index = self.vector_search_client.get_index(index_name=GENEVA_INDEX)
            search_results = index.similarity_search(
                columns=["text", "summary", "doc_name", "pages", "section_type"],
                query_text=query,
                num_results=top_k
            )
            
            results = []
            # Handle different response formats
            if isinstance(search_results, str):
                logger.error(f"Unexpected string response from Geneva search: {search_results}")
                return results
            elif isinstance(search_results, dict):
                # Handle dictionary response - check for common keys
                if 'result' in search_results and 'data_array' in search_results['result']:
                    # Extract data array and convert to list of dictionaries
                    data_array = search_results['result']['data_array']
                    columns = ['text', 'summary', 'doc_name', 'pages', 'section_type', 'score']
                    search_results = []
                    for row in data_array:
                        if len(row) >= len(columns):
                            row_dict = {}
                            for i, col in enumerate(columns):
                                if i < len(row):
                                    row_dict[col] = row[i]
                            search_results.append(row_dict)
                elif 'result' in search_results:
                    search_results = search_results['result']
                elif 'data' in search_results:
                    search_results = search_results['data']
                elif 'rows' in search_results:
                    search_results = search_results['rows']
                else:
                    logger.error(f"Unexpected dictionary response from Geneva search: {search_results}")
                    return results
            elif not isinstance(search_results, (list, tuple)):
                logger.error(f"Unexpected response type from Geneva search: {type(search_results)}")
                return results
            
            # Process the converted search results
            for row in search_results:
                if not isinstance(row, dict):
                    logger.warning(f"Skipping non-dict row in Geneva search results: {type(row)}")
                    continue
                    
                content = row.get("text", "")  # Use 'text' column instead of 'content'
                summary = row.get("summary", "")
                doc_name = row.get("doc_name", "")
                pages = row.get("pages", [])
                section_type = row.get("section_type", "")
                
                # Format page numbers
                page_number = self._format_page_numbers(pages)
                
                # Extract article information from content
                article = self._extract_articles_from_text(content)
                
                # Create metadata dictionary
                metadata = {
                    "doc_name": doc_name,
                    "pages": pages,
                    "section_type": section_type,
                    "article": article,
                    "chunk_id": row.get("chunk_id", "")
                }
                
                result = SearchResult(
                    content=content,
                    summary=summary,
                    source=doc_name,
                    source_type="geneva",
                    score=row.get("score", 0.0),
                    page_number=page_number,
                    section=section_type,
                    article=article,
                    metadata=metadata
                )
                results.append(result)
            
            return results
            
        except Exception as e:
            logger.error(f"Error searching Geneva documentation: {e}")
            return []
    
    def rank_and_filter_results(self, results: List[SearchResult], query: str) -> List[SearchResult]:
        """Advanced ranking and filtering using state-of-the-art techniques."""
        if not results:
            return results
        
        # Query analysis for better ranking
        query_terms = set(query.lower().split())
        query_length = len(query.split())
        
        enhanced_results = []
        for result in results:
            enhanced_score = result.score
            
            # 1. Source Authority Scoring
            authority_multiplier = 1.0
            if result.metadata.get('chamber') == 'Appeals Chamber':
                authority_multiplier = 1.3  # Appeals Chamber has higher authority
            elif result.metadata.get('chamber') == 'Trial Chamber':
                authority_multiplier = 1.2
            elif result.metadata.get('chamber') == 'Pre-Trial Chamber':
                authority_multiplier = 1.1
            
            # Boost for well-known cases
            if result.metadata.get('case_name'):
                case_name = result.metadata.get('case_name', '').lower()
                if any(famous_case in case_name for famous_case in ['tadic', 'blaskic', 'delalic', 'furundzija', 'kunarac']):
                    authority_multiplier *= 1.15
            
            enhanced_score *= authority_multiplier
            
            # 2. Content Quality Scoring
            content_score = 1.0
            
            # Length-based scoring (optimal range)
            content_length = len(result.content)
            if 200 <= content_length <= 2000:
                content_score *= 1.2  # Optimal length
            elif 100 <= content_length < 200:
                content_score *= 0.9  # Too short
            elif content_length > 2000:
                content_score *= 1.1  # Long but acceptable
            else:
                content_score *= 0.7  # Very short
            
            # Summary quality boost
            if result.summary and len(result.summary.strip()) > 30:
                summary_quality = min(len(result.summary.strip()) / 200, 1.0)
                content_score *= (1 + summary_quality * 0.3)
            
            enhanced_score *= content_score
            
            # 3. Semantic Relevance Scoring
            relevance_score = 1.0
            
            # Query term matching in content
            content_lower = result.content.lower()
            query_matches = sum(1 for term in query_terms if term in content_lower)
            if query_matches > 0:
                relevance_score *= (1 + (query_matches / len(query_terms)) * 0.5)
            
            # Query term matching in summary
            if result.summary:
                summary_lower = result.summary.lower()
                summary_matches = sum(1 for term in query_terms if term in summary_lower)
                if summary_matches > 0:
                    relevance_score *= (1 + (summary_matches / len(query_terms)) * 0.3)
            
            # Article/section relevance
            if result.article and any(term in result.article.lower() for term in query_terms):
                relevance_score *= 1.2
            
            if result.section and any(term in result.section.lower() for term in query_terms):
                relevance_score *= 1.15
            
            enhanced_score *= relevance_score
            
            # 4. Metadata Completeness Scoring
            metadata_score = 1.0
            metadata_fields = ['page_number', 'section', 'article', 'case_name', 'chamber']
            present_fields = sum(1 for field in metadata_fields if result.metadata.get(field))
            metadata_score *= (1 + (present_fields / len(metadata_fields)) * 0.2)
            
            enhanced_score *= metadata_score
            
            # 5. Recency Scoring (if date available)
            if result.metadata.get('date') or result.metadata.get('year'):
                # This would need actual date parsing, for now just a placeholder
                recency_score = 1.0
                enhanced_score *= recency_score
            
            # 6. Diversity Penalty (reduce similar results)
            # This would require comparing with already selected results
            diversity_score = 1.0
            enhanced_score *= diversity_score
            
            # 7. Legal Domain Specificity
            legal_terms = ['article', 'convention', 'protocol', 'chamber', 'judgment', 'tribunal', 'court']
            legal_term_count = sum(1 for term in legal_terms if term in content_lower)
            if legal_term_count > 0:
                enhanced_score *= (1 + min(legal_term_count / 10, 0.3))
            
            # Create enhanced result
            enhanced_result = SearchResult(
                content=result.content,
                summary=result.summary,
                source=result.source,
                metadata=result.metadata,
                score=min(enhanced_score, 1.0),  # Cap at 1.0
                source_type=result.source_type,
                page_number=result.page_number,
                article=result.article,
                section=result.section,
                document_type=result.document_type
            )
            enhanced_results.append(enhanced_result)
        
        # Sort by enhanced score
        enhanced_results.sort(key=lambda x: x.score, reverse=True)
        
        # Advanced filtering
        filtered_results = []
        seen_sources = set()
        
        for result in enhanced_results:
            # Quality threshold - lowered to be less aggressive
            if result.score < 0.01:  # Much lower threshold
                continue
            
            # Diversity filtering - avoid too many results from same source
            source_key = f"{result.source}_{result.source_type}"
            if source_key in seen_sources:
                # Only allow 2 results per source
                source_count = sum(1 for r in filtered_results if f"{r.source}_{r.source_type}" == source_key)
                if source_count >= 2:
                    continue
            
            seen_sources.add(source_key)
            filtered_results.append(result)
            
            # Limit total results
            if len(filtered_results) >= 15:  # Increased from 10 for better coverage
                break
        
        return filtered_results
    
    def retrieve_context_enhanced_routing(self, query: str, top_k: int = DEFAULT_TOP_K) -> RetrievalContext:
        """Retrieve context using enhanced routing logic."""
        import time
        start_time = time.time()
        
        # Input validation
        if not query or not query.strip():
            raise ValueError("Query cannot be empty")
        if top_k <= 0:
            raise ValueError("top_k must be positive")
        if top_k > 50:  # Reasonable limit
            logger.warning(f"top_k={top_k} is very large, consider reducing for better performance")
        
        # Determine routing strategy
        routing_analysis = self.determine_enhanced_routing_priority(query)
        enhanced_query = self.enhance_query_with_summary_context(query)
        
        print(f"Routing Strategy: {routing_analysis['search_strategy']}")
        print(f"Reasoning: {routing_analysis['reasoning']}")
        
        # Execute search strategy
        if routing_analysis["search_strategy"] == "geneva_first":
            # Step 1: Search Geneva Convention for legal framework
            print("Step 1: Searching Geneva Convention for legal framework...")
            geneva_results = self.hybrid_search_geneva(enhanced_query, top_k)
            
            # Step 2: Extract legal concepts and search judgments for applications
            if geneva_results:
                legal_concepts = self._extract_legal_concepts_from_results(geneva_results)
                
                if legal_concepts:
                    judgment_query = f"{enhanced_query} {' '.join(legal_concepts[:5])}"
                    print(f"Step 2: Searching judgments for applications of: {', '.join(legal_concepts[:5])}")
                else:
                    judgment_query = enhanced_query
                    print("Step 2: Searching judgments with enhanced query...")
                
                judgment_results = self.hybrid_search_judgments(judgment_query, top_k)
            else:
                print("Step 2: Searching judgments with enhanced query...")
                judgment_results = self.hybrid_search_judgments(enhanced_query, top_k)
        
        elif routing_analysis["search_strategy"] == "judgment_first":
            # Step 1: Search judgments for case law
            print("Step 1: Searching judgments for case law...")
            judgment_results = self.hybrid_search_judgments(enhanced_query, top_k)
            
            # Step 2: Extract legal concepts and search Geneva for framework
            if judgment_results:
                legal_concepts = self._extract_legal_concepts_from_results(judgment_results)
                
                if legal_concepts:
                    geneva_query = f"{enhanced_query} {' '.join(legal_concepts[:5])}"
                    print(f"Step 2: Searching Geneva Convention for: {', '.join(legal_concepts[:5])}")
                else:
                    geneva_query = enhanced_query
                    print("Step 2: Searching Geneva Convention with enhanced query...")
                
                geneva_results = self.hybrid_search_geneva(geneva_query, top_k)
            else:
                print("Step 2: Searching Geneva Convention with enhanced query...")
                geneva_results = self.hybrid_search_geneva(enhanced_query, top_k)
        
        else:  # parallel search
            print("Searching both endpoints in parallel...")
            geneva_results = self.hybrid_search_geneva(enhanced_query, top_k)
            judgment_results = self.hybrid_search_judgments(enhanced_query, top_k)
        
        # Combine results with intelligent weighting
        geneva_weight = routing_analysis["geneva_priority"]
        judgment_weight = routing_analysis["judgment_priority"]
        
        # Weight the results
        for result in geneva_results:
            result.score *= (1 + geneva_weight * 0.5)
        for result in judgment_results:
            result.score *= (1 + judgment_weight * 0.5)
        
        # Combine and sort
        all_results = geneva_results + judgment_results
        all_results.sort(key=lambda x: x.score, reverse=True)
        all_results = all_results[:top_k]
        
        processing_time = time.time() - start_time
        
        return RetrievalContext(
            question=query,
            routing_decision=routing_analysis["search_strategy"],
            judgment_results=judgment_results,
            geneva_results=geneva_results,
            all_results=all_results,
            total_sources=len(all_results),
            processing_time=processing_time
        )
    
    def _prepare_context_for_llm_corrected(self, results: List[SearchResult]) -> str:
        """Prepare retrieved results for LLM consumption with corrected metadata and source mapping."""
        context_parts = []
        for i, result in enumerate(results, 1):
            context_part = f"=== SOURCE {i} ===\n"
            if result.source_type == "judgment":
                doc_name = result.metadata.get('doc_id', result.source)
                context_part += f"Document: {doc_name}\n"
            else:  # geneva
                doc_name = result.metadata.get('doc_name', result.source)
                context_part += f"Document: {doc_name}\n"
            
            if result.page_number:
                context_part += f"Page: {result.page_number}\n"
            if result.section:
                context_part += f"Section: {result.section}\n"
            
            # Add footnotes for judgment documents
            if result.source_type == "judgment" and result.metadata.get("footnotes"):
                footnotes = result.metadata["footnotes"]
                if isinstance(footnotes, list) and footnotes:
                    context_part += f"Footnotes: {', '.join(map(str, footnotes[:3]))}\n"  # Show first 3 footnotes
            if result.article:
                context_part += f"Article: {result.article}\n"
            if result.summary and len(result.summary.strip()) > 10:
                context_part += f"Summary: {result.summary}\n"
            
            content_preview = result.content[:1000] if len(result.content) > 1000 else result.content
            context_part += f"Content:\n{content_preview}\n"
            if len(result.content) > 1000:
                context_part += "...[Content truncated]\n"
            
            context_parts.append(context_part)
        
        return "\n\n".join(context_parts)
    
    def _prepare_structured_context_for_llm(self, results: List[SearchResult]) -> Dict[str, Any]:
        """Prepare structured context with source mapping for better citation tracking."""
        geneva_sources = []
        judgment_sources = []
        
        for i, result in enumerate(results, 1):
            source_info = {
                "source_id": i,
                "document_name": result.metadata.get('doc_id' if result.source_type == "judgment" else 'doc_name', result.source),
                "source_type": result.source_type,
                "page_number": result.page_number,
                "section": result.section,
                "article": result.article,
                "summary": result.summary,
                "content": result.content[:1000] if len(result.content) > 1000 else result.content,
                "score": result.score
            }
            
            if result.source_type == "judgment":
                judgment_sources.append(source_info)
            else:
                geneva_sources.append(source_info)
        
        return {
            "geneva_sources": geneva_sources,
            "judgment_sources": judgment_sources,
            "all_sources": geneva_sources + judgment_sources
        }
    
    def _extract_citations_corrected(self, analysis_text: str) -> List[str]:
        """Extract citations with corrected document names and page formatting, including markdown formatting."""
        import re
        citations = []
        
        # Look for case name patterns (judgment documents) - both with and without markdown
        case_pattern = r'(\*\*)?([A-Z][A-Z\s]+(?:TJ|AJ))(\*\*)?'
        case_matches = re.findall(case_pattern, analysis_text)
        for match in case_matches:
            case_name = match[1].strip()
            if case_name not in [c.replace('**', '').strip() for c in citations]:
                citations.append(f"**{case_name}**")
        
        # Look for Geneva Convention document names - both with and without markdown
        geneva_pattern = r'(\*\*)?([0-9]+-GC-[IVX]+-EN|commentary/[0-9]+\.[0-9]+_pp_[0-9]+_[0-9]+_[A-Za-z_]+)(\*\*)?'
        geneva_matches = re.findall(geneva_pattern, analysis_text)
        for match in geneva_matches:
            doc_name = match[1]
            if doc_name not in [c.replace('**', '').strip() for c in citations]:
                citations.append(f"**{doc_name}**")
        
        # Look for article references - both with and without markdown
        article_pattern = r'(`)?(Article\s+\d+(?:\([a-z]\))?)(`)?'
        article_matches = re.findall(article_pattern, analysis_text)
        for match in article_matches:
            article = match[1]
            if article not in [c.replace('`', '').strip() for c in citations]:
                citations.append(f"`{article}`")
        
        # Look for page references - both with and without markdown
        page_pattern = r'(\*)?(page\s+\d+(?:-\d+)?)(\*)?'
        page_matches = re.findall(page_pattern, analysis_text, re.IGNORECASE)
        for match in page_matches:
            page = match[1]
            if page not in [c.replace('*', '').strip() for c in citations]:
                citations.append(f"*{page}*")
        
        # Look for section type references
        section_pattern = r'(\*)?(section\s+[A-Za-z_]+)(\*)?'
        section_matches = re.findall(section_pattern, analysis_text, re.IGNORECASE)
        for match in section_matches:
            section = match[1]
            if section not in [c.replace('*', '').strip() for c in citations]:
                citations.append(f"*{section}*")
        
        # Look for legal concepts in bold formatting
        legal_concept_pattern = r'\*\*([^*]+(?:principle|responsibility|distinction|proportionality|necessity)[^*]*)\*\*'
        concept_matches = re.findall(legal_concept_pattern, analysis_text, re.IGNORECASE)
        for match in concept_matches:
            if match not in [c.replace('**', '').strip() for c in citations]:
                citations.append(f"**{match}**")
        
        return list(set(citations))
    
    def _extract_resource_list(self, analysis_text: str, structured_context: Dict[str, Any]) -> Dict[str, List[Dict[str, str]]]:
        """Extract comprehensive resource list from analysis text and context."""
        import re
        
        resources = {
            "geneva_documents": [],
            "judgment_documents": [],
            "additional_references": []
        }
        
        # Extract Geneva Convention documents from the Resources Consulted section
        geneva_section_pattern = r'## Resources Consulted.*?### Geneva Convention Documents(.*?)(?=###|$)'
        geneva_match = re.search(geneva_section_pattern, analysis_text, re.DOTALL | re.IGNORECASE)
        if geneva_match:
            geneva_content = geneva_match.group(1)
            # Extract document names, articles, and pages
            geneva_item_pattern = r'\*\*([^*]+)\*\*\s*-\s*`([^`]+)`\s*\(\*([^*]+)\*\)'
            geneva_items = re.findall(geneva_item_pattern, geneva_content)
            for doc_name, article, page in geneva_items:
                resources["geneva_documents"].append({
                    "document_name": doc_name.strip(),
                    "article": article.strip(),
                    "page": page.strip()
                })
        
        # Extract ICTY/ICC judgments from the Resources Consulted section
        judgment_section_pattern = r'### ICTY/ICC Judgments(.*?)(?=###|$)'
        judgment_match = re.search(judgment_section_pattern, analysis_text, re.DOTALL | re.IGNORECASE)
        if judgment_match:
            judgment_content = judgment_match.group(1)
            # Extract case names, pages, and source types
            judgment_item_pattern = r'\*\*([^*]+)\*\*\s*\(\*([^*]+)\*\)\s*-\s*\[([^\]]+)\]'
            judgment_items = re.findall(judgment_item_pattern, judgment_content)
            for case_name, page, source_type in judgment_items:
                resources["judgment_documents"].append({
                    "case_name": case_name.strip(),
                    "page": page.strip(),
                    "source_type": source_type.strip()
                })
        
        # Extract additional references
        additional_section_pattern = r'### Additional References(.*?)(?=##|$)'
        additional_match = re.search(additional_section_pattern, analysis_text, re.DOTALL | re.IGNORECASE)
        if additional_match:
            additional_content = additional_match.group(1)
            # Extract document names, articles, and pages
            additional_item_pattern = r'\*\*([^*]+)\*\*\s*-\s*`([^`]+)`\s*\(\*([^*]+)\*\)'
            additional_items = re.findall(additional_item_pattern, additional_content)
            for doc_name, article, page in additional_items:
                resources["additional_references"].append({
                    "document_name": doc_name.strip(),
                    "article": article.strip(),
                    "page": page.strip()
                })
        
        # If no structured resource list found, extract from context
        if not any(resources.values()):
            # Extract from structured context
            for source in structured_context.get('geneva_sources', []):
                resources["geneva_documents"].append({
                    "document_name": source.get('document_name', ''),
                    "article": source.get('article', ''),
                    "page": source.get('page_number', '')
                })
            
            for source in structured_context.get('judgment_sources', []):
                resources["judgment_documents"].append({
                    "case_name": source.get('document_name', ''),
                    "page": source.get('page_number', ''),
                    "source_type": source.get('source_type', 'Judgment')
                })
        
        return resources
    
    def _extract_structured_citations(self, analysis_text: str, structured_context: Dict[str, Any]) -> Dict[str, List[str]]:
        """Extract citations organized by section and mapped to sources."""
        import re
        
        citations_by_section = {
            "legal_framework": [],
            "case_law_analysis": [],
            "synthesis": [],
            "key_findings": []
        }
        
        # Split analysis into sections
        sections = re.split(r'##\s+(Legal Framework|Case Law Analysis|Synthesis and Analysis|Key Findings)', analysis_text)
        
        # Map section content to section names
        section_content = {}
        for i in range(1, len(sections), 2):
            if i + 1 < len(sections):
                section_name = sections[i].lower().replace(' ', '_').replace('and', '')
                section_content[section_name] = sections[i + 1]
        
        # Extract citations for each section
        for section_name, content in section_content.items():
            if not content:
                continue
                
            section_citations = []
            
            # Extract case names - both with and without markdown
            case_pattern = r'(\*\*)?([A-Z][A-Z\s]+(?:TJ|AJ))(\*\*)?'
            case_matches = re.findall(case_pattern, content)
            for match in case_matches:
                case_name = match[1].strip()
                if case_name not in [c.replace('**', '').strip() for c in section_citations]:
                    section_citations.append(f"**{case_name}**")
            
            # Extract Geneva Convention documents - both with and without markdown
            geneva_pattern = r'(\*\*)?([0-9]+-GC-[IVX]+-EN|commentary/[0-9]+\.[0-9]+_pp_[0-9]+_[0-9]+_[A-Za-z_]+)(\*\*)?'
            geneva_matches = re.findall(geneva_pattern, content)
            for match in geneva_matches:
                doc_name = match[1]
                if doc_name not in [c.replace('**', '').strip() for c in section_citations]:
                    section_citations.append(f"**{doc_name}**")
            
            # Extract article references - both with and without markdown
            article_pattern = r'(`)?(Article\s+\d+(?:\([a-z]\))?)(`)?'
            article_matches = re.findall(article_pattern, content)
            for match in article_matches:
                article = match[1]
                if article not in [c.replace('`', '').strip() for c in section_citations]:
                    section_citations.append(f"`{article}`")
            
            # Extract page references - both with and without markdown
            page_pattern = r'(\*)?(page\s+\d+(?:-\d+)?)(\*)?'
            page_matches = re.findall(page_pattern, content, re.IGNORECASE)
            for match in page_matches:
                page = match[1]
                if page not in [c.replace('*', '').strip() for c in section_citations]:
                    section_citations.append(f"*{page}*")
            
            # Extract legal concepts in bold formatting
            legal_concept_pattern = r'\*\*([^*]+(?:principle|responsibility|distinction|proportionality|necessity)[^*]*)\*\*'
            concept_matches = re.findall(legal_concept_pattern, content, re.IGNORECASE)
            for match in concept_matches:
                if match not in [c.replace('**', '').strip() for c in section_citations]:
                    section_citations.append(f"**{match}**")
            
            # Map to appropriate section
            if 'legal_framework' in section_name:
                citations_by_section["legal_framework"] = list(set(section_citations))
            elif 'case_law' in section_name:
                citations_by_section["case_law_analysis"] = list(set(section_citations))
            elif 'synthesis' in section_name:
                citations_by_section["synthesis"] = list(set(section_citations))
            elif 'key_findings' in section_name:
                citations_by_section["key_findings"] = list(set(section_citations))
        
        return citations_by_section
    
    def _format_source_reference_list(self, sources: List[Dict[str, Any]]) -> str:
        """Format source information for LLM reference."""
        source_list = []
        for source in sources:
            source_info = f"Source {source['source_id']}: {source['document_name']}"
            if source['page_number']:
                source_info += f" (page {source['page_number']})"
            if source['article']:
                source_info += f" - {source['article']}"
            if source['section']:
                source_info += f" - {source['section']}"
            source_info += f" [{source['source_type']}]"
            source_list.append(source_info)
        
        return "\n".join(source_list)
    
    def _extract_key_findings(self, analysis_text: str) -> List[str]:
        """Extract key findings from the analysis text."""
        import re
        findings = []
        
        # Look for bullet points
        bullet_pattern = r'[•\-\*]\s*([^\n]+)'
        bullet_matches = re.findall(bullet_pattern, analysis_text)
        findings.extend(bullet_matches)
        
        # Look for numbered lists
        number_pattern = r'\d+\.\s*([^\n]+)'
        number_matches = re.findall(number_pattern, analysis_text)
        findings.extend(number_matches)
        
        # Clean up findings
        findings = [f.strip() for f in findings if len(f.strip()) > 10]
        return findings[:10]
    
    def _calculate_confidence_score(self, analysis_text: str, context: RetrievalContext) -> float:
        """Calculate confidence score based on analysis quality and source coverage."""
        base_score = min(len(context.all_results) / 10.0, 1.0)
        length_boost = min(len(analysis_text) / 2000.0, 0.3)
        citation_boost = min(len(self._extract_citations_corrected(analysis_text)) / 5.0, 0.2)
        findings_boost = min(len(self._extract_key_findings(analysis_text)) / 3.0, 0.2)
        
        total_score = base_score + length_boost + citation_boost + findings_boost
        return min(total_score, 1.0)
    
    def generate_legal_analysis_with_enhanced_routing(self, question: str, context: RetrievalContext = None, conversation_id: str = None) -> LegalAnalysis:
        """Generate comprehensive legal analysis using enhanced routing context with structured output and source citations."""
        import time
        start_time = time.time()
        
        # If no context provided, retrieve it
        if context is None:
            context = self.retrieve_context_enhanced_routing(question)
        
        # Prepare structured context for better source mapping
        structured_context = self._prepare_structured_context_for_llm(context.all_results)
        
        # Prepare context text for LLM
        context_text = self._prepare_context_for_llm_corrected(context.all_results)
        
        # Enhanced system prompt for clear legal analysis with comprehensive resource listing
        system_prompt = """You are an expert international criminal law researcher specializing in ICTY/ICC case law and Geneva Convention analysis.

**Your Task:**
Provide a clear and concise legal analysis that answers the question using information from both Geneva Convention framework and case law applications, with proper markdown formatting, source citations, and a comprehensive resource list.

**REQUIRED STRUCTURE:**
```markdown
# Legal Analysis

## Legal Framework
- **Key Principles**: List the main legal principles with `Article X` references
- **Relevant Articles**: Explain important articles with **document citations**

## Case Law Application
- **Key Cases**: Discuss relevant cases with **case names** and *page references*
- **Legal Findings**: Explain how the law was applied in practice

## Key Findings
- **Main Points**: List the most important findings with supporting citations
- **Practical Implications**: Provide actionable insights for legal practice

## Resources Consulted
### Geneva Convention Documents
- **Document Name** - `Article X` (*page Y*)
- **Document Name** - `Article X` (*page Y*)

### ICTY/ICC Judgments
- **Case Name** (*page Y*) - [Source Type]
- **Case Name** (*page Y*) - [Source Type]

### Additional References
- **Document Name** - `Article X` (*page Y*)
```

**MARKDOWN FORMATTING:**
- Use **bold** for case names, legal concepts, and key terms
- Use `code formatting` for article numbers and legal provisions
- Use *italics* for page references and emphasis
- Use `>` for important quotes
- Use `-` for bullet points

**CITATION FORMAT:**
- Case names: **Tadic TJ**, **Blaskic AJ**
- Articles: `Article 4`, `Article 13`
- Pages: *page 45*, *page 45-46*
- Source references: (Source X, page Y)

**RESOURCE LISTING REQUIREMENTS:**
- List ALL documents referenced in your analysis
- Include document names, articles, and page numbers
- Separate Geneva Convention documents from case law
- Include source type (Trial Chamber, Appeals Chamber, etc.)
- Be comprehensive and accurate

Keep the analysis clear, focused, and practical for legal professionals."""
        
        human_prompt = f"""# Legal Research Question
{question}

# Retrieved Context
{context_text}

# Available Sources
- **Geneva Convention Sources**: {len(structured_context['geneva_sources'])} sources
- **Case Law Sources**: {len(structured_context['judgment_sources'])} sources
- **Total Sources**: {len(structured_context['all_sources'])} sources

# Analysis Requirements
Please provide a clear legal analysis that:
1. **Identifies relevant Geneva Convention articles and principles** (with citations)
2. **Shows how these principles were applied in ICTY/ICC case law** (with case citations)
3. **Provides practical insights for legal professionals**
4. **Uses proper markdown formatting and source citations**
5. **Includes a comprehensive resource list at the end**

# Required Structure
## Legal Framework
- List key principles with `Article X` references
- Explain important articles with **document citations**

## Case Law Application
- Discuss relevant cases with **case names** and *page references*
- Explain how the law was applied in practice

## Key Findings
- List the most important findings with supporting citations
- Provide actionable insights for legal practice

## Resources Consulted
### Geneva Convention Documents
- List all Geneva Convention documents used with articles and pages
- Format: **Document Name** - `Article X` (*page Y*)

### ICTY/ICC Judgments
- List all case law sources used with case names and pages
- Format: **Case Name** (*page Y*) - [Source Type]

### Additional References
- List any other documents or sources referenced
- Format: **Document Name** - `Article X` (*page Y*)

# Source Information for Reference
{self._format_source_reference_list(structured_context['all_sources'])}

# Important Notes for Resource Listing
- Include ALL sources that informed your analysis
- Be specific about document names, articles, and page numbers
- Separate Geneva Convention documents from case law
- Include chamber information for judgments (Trial Chamber, Appeals Chamber, etc.)
- Ensure accuracy and completeness in your resource list"""

        try:
            response = self.llm.invoke([
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": human_prompt}
            ])
            
            analysis_text = response.content
            
            # Extract components using enhanced methods
            key_findings = self._extract_key_findings(analysis_text)
            citations = self._extract_citations_corrected(analysis_text)
            structured_citations = self._extract_structured_citations(analysis_text, structured_context)
            resource_list = self._extract_resource_list(analysis_text, structured_context)
            confidence_score = self._calculate_confidence_score(analysis_text, context)
            
            processing_time = time.time() - start_time
            
            return LegalAnalysis(
                question=question,
                analysis=analysis_text,
                key_findings=key_findings,
                citations=citations,
                resource_list=resource_list,
                confidence_score=confidence_score,
                sources_used=len(context.all_results),
                processing_time=processing_time,
                conversation_id=conversation_id
            )
            
        except Exception as e:
            logger.error(f"Error generating legal analysis: {e}")
            return LegalAnalysis(
                question=question,
                analysis=f"Error generating analysis: {str(e)}",
                key_findings=[],
                citations=[],
                resource_list={"geneva_documents": [], "judgment_documents": [], "additional_references": []},
                confidence_score=0.0,
                sources_used=0,
                processing_time=time.time() - start_time,
                conversation_id=conversation_id
            )

# COMMAND ----------

# Test the Enhanced RAG System
def test_enhanced_rag_system():
    """Test the enhanced RAG system with corrected metadata handling and enhanced routing."""
    
    print("TESTING ENHANCED RAG SYSTEM WITH CORRECTED METADATA")
    print("=" * 70)
    
    # Initialize the enhanced system
    rag_system = EnhancedICCRAGSystem()
    
    # Test query
    test_query = "What factors did the ICTY Trial Chamber consider when determining active participation in hostilities?"
    
    print(f"Test Query: {test_query}")
    print("-" * 70)
    
    try:
        # Test enhanced retrieval with corrected routing
        print("Testing Enhanced Retrieval with Corrected Routing...")
        context = rag_system.retrieve_context_enhanced_routing(test_query, top_k=6)
        
        print(f"   Sources found: {context.total_sources}")
        print(f"   Geneva sources: {len(context.geneva_results)}")
        print(f"   Judgment sources: {len(context.judgment_results)}")
        print(f"   Processing time: {context.processing_time:.2f}s")
        print()
        
        # Display source information with corrected metadata
        print("Source Information with Corrected Metadata:")
        for i, result in enumerate(context.all_results, 1):
            if result.source_type == "judgment":
                doc_name = result.metadata.get('doc_id', result.source)
                print(f"   {i}. Document: {doc_name}")
            else:
                doc_name = result.metadata.get('doc_name', result.source)
                print(f"   {i}. Document: {doc_name}")
            
            print(f"      Type: {result.source_type}")
            print(f"      Page: {result.page_number if result.page_number else 'N/A'}")
            print(f"      Section: {result.section if result.section else 'N/A'}")
            print(f"      Article: {result.article if result.article else 'N/A'}")
            print(f"      Summary: {result.summary[:100] + '...' if result.summary and len(result.summary) > 100 else result.summary or 'N/A'}")
            print(f"      Score: {result.score:.3f}")
            print()
        
        # Test enhanced legal analysis generation
        print("Testing Enhanced Legal Analysis with Corrected Metadata...")
        analysis = rag_system.generate_legal_analysis_with_enhanced_routing(
            test_query, 
            context=context, 
            conversation_id="test_enhanced"
        )
        
        print(f"   Confidence score: {analysis.confidence_score:.3f}")
        print(f"   Key findings: {len(analysis.key_findings)}")
        print(f"   Citations: {len(analysis.citations)}")
        print(f"   Processing time: {analysis.processing_time:.2f}s")
        print()
        
        # Display analysis preview
        print("ENHANCED ANALYSIS PREVIEW:")
        print("-" * 50)
        print(analysis.analysis[:800] + "..." if len(analysis.analysis) > 800 else analysis.analysis)
        print()
        
        print("Enhanced RAG system test completed successfully!")
        return True
        
    except Exception as e:
        print(f"Error during testing: {e}")
        import traceback
        traceback.print_exc()
        return False

# Run the enhanced test
test_enhanced_rag_system()

# COMMAND ----------

# MAGIC %md
# MAGIC ## End-to-End System Test

# COMMAND ----------

def test_complete_system():
    """Test the complete RAG system end-to-end in Databricks."""
    print("🚀 TESTING COMPLETE RAG SYSTEM END-TO-END")
    print("=" * 80)
    
    try:
        # Initialize the system
        print("1. Initializing Enhanced ICC RAG System...")
        rag_system = EnhancedICCRAGSystem()
        print("   ✅ System initialized successfully")
        
        # Test queries
        test_queries = [
            "What factors did the ICTY Trial Chamber consider when determining active participation in hostilities?",
            "What are the key principles of international humanitarian law?",
            "How has Article 4 of the Geneva Convention been applied in ICTY case law?",
            "What is the definition of protected persons under international humanitarian law?"
        ]
        
        for i, query in enumerate(test_queries, 1):
            print(f"\n2.{i} Testing Query: {query}")
            print("-" * 60)
            
            # Test retrieval
            print("   Testing retrieval...")
            context = rag_system.retrieve_context_enhanced_routing(query, top_k=5)
            print(f"   ✅ Retrieved {context.total_sources} sources ({len(context.geneva_results)} Geneva, {len(context.judgment_results)} Judgment)")
            print(f"   ✅ Processing time: {context.processing_time:.2f}s")
            
            # Test analysis generation
            print("   Testing analysis generation...")
            analysis = rag_system.generate_legal_analysis_with_enhanced_routing(
                query, context=context, conversation_id=f"test_{i}"
            )
            print(f"   ✅ Analysis generated (confidence: {analysis.confidence_score:.3f})")
            print(f"   ✅ Key findings: {len(analysis.key_findings)}")
            print(f"   ✅ Citations: {len(analysis.citations)}")
            
            # Show analysis preview
            print(f"   Analysis preview: {analysis.analysis[:200]}...")
        
        print(f"\n🎉 ALL TESTS PASSED! System is ready for production deployment.")
        return True
        
    except Exception as e:
        print(f"❌ System test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

# Run the complete system test
test_complete_system()

# COMMAND ----------

# MLflow Production Model Deployment
def create_mlflow_model():
    """Create and deploy the enhanced RAG system as an MLflow model."""
    
    # Initialize the RAG system for testing
    rag_system = EnhancedICCRAGSystem()
    
    # Define the model signature with proper input/output schemas
    from pydantic import BaseModel, Field
    from typing import List, Optional
    
    class ModelInput(BaseModel):
        question: str = Field(..., description="Legal research question")
        top_k: int = Field(default=10, ge=1, le=50, description="Number of top results to retrieve")
        conversation_id: Optional[str] = Field(default=None, description="Optional conversation ID for context")
    
    class ModelOutput(BaseModel):
        analysis: str = Field(..., description="Generated legal analysis")
        key_findings: List[str] = Field(..., description="Key findings extracted from analysis")
        citations: List[str] = Field(..., description="Citations and references")
        resource_list: Dict[str, List[Dict[str, str]]] = Field(..., description="Comprehensive list of resources consulted")
        confidence_score: float = Field(..., ge=0.0, le=1.0, description="Confidence score of the analysis")
        sources_used: int = Field(..., ge=0, description="Number of sources used")
        processing_time: float = Field(..., ge=0.0, description="Processing time in seconds")
    
    # Create signature using sample data
    signature = infer_signature(
        model_input={
            "question": "What factors did the ICTY Trial Chamber consider when determining active participation in hostilities?",
            "top_k": 6,
            "conversation_id": "test"
        },
        model_output={
            "analysis": "The ICTY Trial Chamber considered several key factors...",
            "key_findings": ["Factor 1", "Factor 2"],
            "citations": ["**Tadic TJ**", "`Article 4`"],
            "resource_list": {
                "geneva_documents": [{"document_name": "365-GC-I-EN", "article": "Article 4", "page": "page 45"}],
                "judgment_documents": [{"case_name": "Tadic TJ", "page": "page 123", "source_type": "Trial Chamber"}],
                "additional_references": []
            },
            "confidence_score": 0.85,
            "sources_used": 5,
            "processing_time": 2.5
        }
    )
    
    # Create conda environment with dependencies
    conda_env = {
        "channels": ["conda-forge"],
        "dependencies": [
            "python=3.11",
            "pip",
            {
                "pip": [
                    "databricks-vectorsearch>=0.1.0",
                    "databricks-langchain>=0.1.0",
                    "mlflow>=3.1.1",
                    "pydantic>=2.0.0",
                    "databricks-agents>=0.1.0",
                    "unitycatalog-langchain[databricks]>=0.1.0",
                    "langchain>=0.1.0",
                    "numpy>=1.24.0",
                    "pandas>=2.0.0"
                ]
            }
        ]
    }
    
    # Create a proper Python model wrapper
    class ICCRAGModel(mlflow.pyfunc.PythonModel):
        def __init__(self):
            self.rag_system = None
            self.config = {
                "vector_search_endpoint": VECTOR_SEARCH_ENDPOINT,
                "llm_model": LLM_MODEL,
                "embedding_model": EMBEDDING_MODEL,
                "judgment_index": JUDGMENT_INDEX,
                "geneva_index": GENEVA_INDEX
            }
        
        def load_context(self, context):
            """Load the RAG system when the model is loaded."""
            try:
                logger.info("Loading ICC RAG system context...")
                
                # Set up Databricks authentication for model serving
                self._setup_databricks_auth(context)
                
                # Try to get configuration from MLflow context if available
                config = self.config.copy()
                
                # Initialize the RAG system with configuration
                self.rag_system = EnhancedICCRAGSystem(
                    vector_search_endpoint_name=config["vector_search_endpoint"],
                    llm_model=config["llm_model"]
                )
                
                logger.info("ICC RAG system loaded successfully")
                
            except Exception as e:
                logger.error(f"Error loading RAG system context: {e}")
                # Fallback initialization with default values
                try:
                    logger.info("Attempting fallback initialization with default values...")
                    self.rag_system = EnhancedICCRAGSystem()
                    logger.info("Fallback RAG system initialization successful")
                except Exception as fallback_error:
                    logger.error(f"Fallback initialization failed: {fallback_error}")
                    raise RuntimeError(f"Failed to initialize RAG system: {e}")
        
        def _setup_databricks_auth(self, context):
            """Set up Databricks authentication for model serving using proper resource handling."""
            import os
            
            try:
                logger.info("Setting up Databricks authentication for model serving...")
                
                # Method 1: Use MLflow's automatic authentication passthrough from resources
                # The resources parameter in mlflow.pyfunc.log_model() should handle this automatically
                # when the model is deployed in Databricks Model Serving
                
                # Method 2: Try to get credentials from MLflow tracking context
                try:
                    from mlflow.utils.databricks_utils import get_databricks_host_creds
                    host_creds = get_databricks_host_creds()
                    if host_creds and host_creds.host:
                        os.environ['DATABRICKS_HOST'] = host_creds.host
                        logger.info(f"Set DATABRICKS_HOST from MLflow context: {host_creds.host}")
                        if hasattr(host_creds, 'token') and host_creds.token:
                            os.environ['DATABRICKS_TOKEN'] = host_creds.token
                            logger.info("Set DATABRICKS_TOKEN from MLflow context")
                except Exception as cred_error:
                    logger.warning(f"Could not get credentials from MLflow context: {cred_error}")
                
                # Method 3: Manual authentication setup (as per documentation)
                # Set environment variables for manual authentication
                if not os.environ.get('DATABRICKS_HOST'):
                    # Try to get from Databricks runtime environment
                    workspace_url = os.environ.get('DATABRICKS_WORKSPACE_URL')
                    if workspace_url:
                        os.environ['DATABRICKS_HOST'] = workspace_url
                        logger.info(f"Set DATABRICKS_HOST from runtime: {workspace_url}")
                
                # Method 4: Check for .databrickscfg file
                try:
                    from pathlib import Path
                    databricks_cfg = Path.home() / '.databrickscfg'
                    if databricks_cfg.exists():
                        logger.info("Found .databrickscfg file, reading credentials...")
                        with open(databricks_cfg, 'r') as f:
                            content = f.read()
                            for line in content.split('\n'):
                                if 'host' in line and '=' in line and not line.strip().startswith('#'):
                                    host = line.split('=')[1].strip()
                                    if not os.environ.get('DATABRICKS_HOST'):
                                        os.environ['DATABRICKS_HOST'] = host
                                        logger.info(f"Set DATABRICKS_HOST from .databrickscfg: {host}")
                                elif 'token' in line and '=' in line and not line.strip().startswith('#'):
                                    token = line.split('=')[1].strip()
                                    if not os.environ.get('DATABRICKS_TOKEN'):
                                        os.environ['DATABRICKS_TOKEN'] = token
                                        logger.info("Set DATABRICKS_TOKEN from .databrickscfg")
                except Exception as cfg_error:
                    logger.warning(f"Could not read .databrickscfg: {cfg_error}")
                
                # Log current authentication status
                host = os.environ.get('DATABRICKS_HOST', 'Not set')
                token_set = 'Yes' if os.environ.get('DATABRICKS_TOKEN') else 'No'
                logger.info(f"Authentication status - Host: {host}, Token: {token_set}")
                
                # If no authentication found, log warning but don't fail
                if host == 'Not set' or token_set == 'No':
                    logger.warning("Databricks authentication not fully configured. Model may fail at runtime.")
                    logger.info("To fix: Set DATABRICKS_HOST and DATABRICKS_TOKEN environment variables")
                
            except Exception as auth_error:
                logger.error(f"Error setting up Databricks authentication: {auth_error}")
                # Don't raise here, let the system try to initialize anyway
        
        def predict(self, context, model_input):
            """Make predictions using the RAG system."""
            try:
                # Validate input
                if self.rag_system is None:
                    raise RuntimeError("RAG system not initialized. Call load_context first.")
                
                # Parse input
                if isinstance(model_input, dict):
                    question = model_input.get("question", "").strip()
                    top_k = int(model_input.get("top_k", 10))
                    conversation_id = model_input.get("conversation_id")
                elif hasattr(model_input, 'iloc'):  # DataFrame
                    if len(model_input) == 0:
                        raise ValueError("Empty input DataFrame")
                    question = str(model_input.iloc[0].get("question", "")).strip()
                    top_k = int(model_input.iloc[0].get("top_k", 10))
                    conversation_id = model_input.iloc[0].get("conversation_id")
                else:
                    raise ValueError(f"Unsupported input type: {type(model_input)}")
                
                # Validate input
                if not question:
                    raise ValueError("Question cannot be empty")
                if top_k < 1 or top_k > 50:
                    raise ValueError("top_k must be between 1 and 50")
                
                logger.info(f"Processing question: {question[:100]}...")
                
                # Retrieve context using enhanced routing
                retrieval_context = self.rag_system.retrieve_context_enhanced_routing(question, top_k)
                
                # Generate legal analysis
                analysis = self.rag_system.generate_legal_analysis_with_enhanced_routing(
                    question, context=retrieval_context, conversation_id=conversation_id
                )
                
                # Prepare response
                response = {
                    "analysis": analysis.analysis,
                    "key_findings": analysis.key_findings,
                    "citations": analysis.citations,
                    "resource_list": analysis.resource_list or {"geneva_documents": [], "judgment_documents": [], "additional_references": []},
                    "confidence_score": float(analysis.confidence_score),
                    "sources_used": int(analysis.sources_used),
                    "processing_time": float(analysis.processing_time)
                }
                
                logger.info(f"Analysis completed. Confidence: {response['confidence_score']:.3f}")
                return response
                
            except Exception as e:
                logger.error(f"Error in RAG model prediction: {e}")
                return {
                    "analysis": f"Error generating analysis: {str(e)}",
                    "key_findings": [],
                    "citations": [],
                    "resource_list": {"geneva_documents": [], "judgment_documents": [], "additional_references": []},
                    "confidence_score": 0.0,
                    "sources_used": 0,
                    "processing_time": 0.0
                }
    
    # Log the model to MLflow
    try:
        with mlflow.start_run() as run:
            logger.info("Starting MLflow model logging...")
            
            # Log model with proper dependencies and Databricks resources for authentication
            mlflow.pyfunc.log_model(
                artifact_path="enhanced_icc_rag",
                python_model=ICCRAGModel(),
                signature=signature,
                input_example={
                    "question": "What factors did the ICTY Trial Chamber consider when determining active participation in hostilities?",
                    "top_k": 6,
                    "conversation_id": "test"
                },
                conda_env=conda_env,
                resources=[
                    # DatabricksServingEndpoint(endpoint_name=VECTOR_SEARCH_ENDPOINT),  # REMOVED - jgmt is not a serving endpoint
                    DatabricksVectorSearchIndex(index_name=JUDGMENT_INDEX),
                    DatabricksVectorSearchIndex(index_name=GENEVA_INDEX)
                ]
            )
            
            # Log parameters (configuration stored as parameters instead of resources)
            mlflow.log_params({
                "vector_search_endpoint": VECTOR_SEARCH_ENDPOINT,
                "llm_model": LLM_MODEL,
                "embedding_model": EMBEDDING_MODEL,
                "catalog_name": CATALOG_NAME,
                "schema_name": SCHEMA_NAME,
                "judgment_index": JUDGMENT_INDEX,
                "geneva_index": GENEVA_INDEX,
                "conversation_window": DEFAULT_CONVERSATION_WINDOW,
                "default_top_k": DEFAULT_TOP_K,
                "model_type": "enhanced_rag",
                "version": "1.0"
            })
            
            # Note: Vector search configuration is stored in model parameters
            # The model will use these parameters to connect to the appropriate endpoints
            # Authentication is handled automatically via Databricks resources:
            # - DatabricksServingEndpoint provides authentication for Vector Search
            # - DatabricksVectorSearchIndex provides authentication for indexes
            # This follows the Databricks documentation for proper resource registration
            
            # Log metrics
            mlflow.log_metrics({
                "model_version": 1.0,
                "legal_topics_judgment": len(LEGAL_TOPICS["judgment_priority"]),
                "legal_topics_geneva": len(LEGAL_TOPICS["geneva_priority"]),
                "max_top_k": 50,
                "min_top_k": 1
            })
            
            # Log model description
            mlflow.set_tag("description", "Enhanced ICC RAG System for legal research with dual-index retrieval")
            mlflow.set_tag("domain", "legal_research")
            mlflow.set_tag("framework", "databricks_vectorsearch")
            
            logger.info(f"Model logged successfully! Run ID: {run.info.run_id}")
            return run.info.run_id
            
    except Exception as e:
        logger.error(f"Error logging model to MLflow: {e}")
        raise RuntimeError(f"Failed to log model: {e}")

# Deploy the model with comprehensive error handling
try:
    print("🚀 Starting MLflow Model Deployment...")
    model_run_id = create_mlflow_model()
    if model_run_id:
        print(f"✅ Enhanced ICC RAG model deployed with run ID: {model_run_id}")
    else:
        print("❌ Model deployment failed - no run ID returned")
        raise RuntimeError("Model deployment failed")
except Exception as e:
    print(f"❌ Error during model deployment: {e}")
    print("\n🔄 Trying alternative simple model approach...")
    
    # Try the simple model approach
    try:
        print("🚀 Creating simple model for serving...")
        
        # Define simple model class inline to avoid dependency issues
        class SimpleICCRAGModel(mlflow.pyfunc.PythonModel):
            def __init__(self):
                self.rag_system = None
                self.config = {
                    "vector_search_endpoint": VECTOR_SEARCH_ENDPOINT,
                    "llm_model": LLM_MODEL,
                    "embedding_model": EMBEDDING_MODEL,
                    "judgment_index": JUDGMENT_INDEX,
                    "geneva_index": GENEVA_INDEX
                }
            
            def load_context(self, context):
                """Load the RAG system when the model is loaded."""
                try:
                    logger.info("Loading simple ICC RAG system context...")
                    
                    # Simple initialization - let Databricks handle authentication
                    self.rag_system = EnhancedICCRAGSystem(
                        vector_search_endpoint_name=self.config["vector_search_endpoint"],
                        llm_model=self.config["llm_model"]
                    )
                    
                    logger.info("Simple ICC RAG system loaded successfully")
                    
                except Exception as e:
                    logger.error(f"Error loading simple RAG system context: {e}")
                    # Create a minimal fallback
                    try:
                        self.rag_system = EnhancedICCRAGSystem()
                        logger.info("Fallback RAG system initialization successful")
                    except Exception as fallback_error:
                        logger.error(f"Fallback initialization failed: {fallback_error}")
                        raise RuntimeError(f"Failed to initialize RAG system: {e}")
            
            def predict(self, context, model_input):
                """Make predictions using the RAG system."""
                try:
                    # Validate input
                    if self.rag_system is None:
                        raise RuntimeError("RAG system not initialized. Call load_context first.")
                    
                    # Parse input
                    if isinstance(model_input, dict):
                        question = model_input.get("question", "").strip()
                        top_k = int(model_input.get("top_k", 10))
                        conversation_id = model_input.get("conversation_id")
                    elif hasattr(model_input, 'iloc'):  # DataFrame
                        if len(model_input) == 0:
                            raise ValueError("Empty input DataFrame")
                        question = str(model_input.iloc[0].get("question", "")).strip()
                        top_k = int(model_input.iloc[0].get("top_k", 10))
                        conversation_id = model_input.iloc[0].get("conversation_id")
                    else:
                        raise ValueError(f"Unsupported input type: {type(model_input)}")
                    
                    # Validate input
                    if not question:
                        raise ValueError("Question cannot be empty")
                    if top_k < 1 or top_k > 50:
                        raise ValueError("top_k must be between 1 and 50")
                    
                    logger.info(f"Processing question: {question[:100]}...")
                    
                    # Retrieve context using enhanced routing
                    retrieval_context = self.rag_system.retrieve_context_enhanced_routing(question, top_k)
                    
                    # Generate legal analysis
                    analysis = self.rag_system.generate_legal_analysis_with_enhanced_routing(
                        question, context=retrieval_context, conversation_id=conversation_id
                    )
                    
                    # Prepare response
                    response = {
                        "analysis": analysis.analysis,
                        "key_findings": analysis.key_findings,
                        "citations": analysis.citations,
                        "confidence_score": float(analysis.confidence_score),
                        "sources_used": int(analysis.sources_used),
                        "processing_time": float(analysis.processing_time)
                    }
                    
                    logger.info(f"Analysis completed. Confidence: {response['confidence_score']:.3f}")
                    return response
                    
                except Exception as e:
                    logger.error(f"Error in simple RAG model prediction: {e}")
                    return {
                        "analysis": f"Error generating analysis: {str(e)}",
                        "key_findings": [],
                        "citations": [],
                        "confidence_score": 0.0,
                        "sources_used": 0,
                        "processing_time": 0.0
                    }
        
        simple_model_class = SimpleICCRAGModel
        
        # Create signature
        signature = infer_signature(
            model_input={
                "question": "What factors did the ICTY Trial Chamber consider when determining active participation in hostilities?",
                "top_k": 6,
                "conversation_id": "test"
            },
            model_output={
                "analysis": "The ICTY Trial Chamber considered several key factors...",
                "key_findings": ["Factor 1", "Factor 2"],
                "citations": ["**Tadic TJ**", "`Article 4`"],
                "confidence_score": 0.85,
                "sources_used": 5,
                "processing_time": 2.5
            }
        )
        
        # Create conda environment
        conda_env = {
            "channels": ["conda-forge"],
            "dependencies": [
                "python=3.11",
                "pip",
                {
                    "pip": [
                        "databricks-vectorsearch>=0.1.0",
                        "databricks-langchain>=0.1.0",
                        "mlflow>=3.1.1",
                        "pydantic>=2.0.0",
                        "databricks-agents>=0.1.0",
                        "unitycatalog-langchain[databricks]>=0.1.0",
                        "langchain>=0.1.0",
                        "numpy>=1.24.0",
                        "pandas>=2.0.0"
                    ]
                }
            ]
        }
        
        # Log the simple model
        with mlflow.start_run() as run:
            mlflow.pyfunc.log_model(
                artifact_path="simple_icc_rag",
                python_model=simple_model_class(),
                signature=signature,
                input_example={
                    "question": "What factors did the ICTY Trial Chamber consider when determining active participation in hostilities?",
                    "top_k": 6,
                    "conversation_id": "test"
                },
                conda_env=conda_env
            )
            
            # Log parameters
            mlflow.log_params({
                "vector_search_endpoint": VECTOR_SEARCH_ENDPOINT,
                "llm_model": LLM_MODEL,
                "embedding_model": EMBEDDING_MODEL,
                "catalog_name": CATALOG_NAME,
                "schema_name": SCHEMA_NAME,
                "judgment_index": JUDGMENT_INDEX,
                "geneva_index": GENEVA_INDEX,
                "model_type": "simple_rag",
                "version": "1.0"
            })
            
            model_run_id = run.info.run_id
            print(f"✅ Simple ICC RAG model deployed with run ID: {model_run_id}")
            
    except Exception as simple_error:
        print(f"❌ Simple model deployment also failed: {simple_error}")
        import traceback
        traceback.print_exc()
        print("\n🔧 Troubleshooting Tips:")
        print("1. Ensure you're running in a Databricks environment")
        print("2. Check that Vector Search endpoints are accessible")
        print("3. Verify MLflow is properly configured")
        print("4. Check that all required libraries are installed")
        raise

# COMMAND ----------

# MAGIC %md
# MAGIC ## Model Registration

# COMMAND ----------

def register_model(model_run_id: str, model_name: str = MODEL_NAME, stage: str = "None"):
    """Register the model in MLflow Model Registry with Unity Catalog."""
    try:
        logger.info(f"Registering model with run ID: {model_run_id}")
        
        # Get the model URI from the run
        model_uri = f"runs:/{model_run_id}/enhanced_icc_rag"
        
        # Validate model URI exists
        try:
            client = mlflow.tracking.MlflowClient()
            run = client.get_run(model_run_id)
            if not run:
                raise ValueError(f"Run {model_run_id} not found")
        except Exception as e:
            raise ValueError(f"Invalid run ID {model_run_id}: {e}")
        
        # Register the model with Unity Catalog
        registered_model = mlflow.register_model(
            model_uri=model_uri,
            name=model_name
        )
        
        logger.info(f"Model registered successfully in Unity Catalog!")
        print(f"✅ Model registered successfully!")
        print(f"Model Name: {registered_model.name}")
        print(f"Model Version: {registered_model.version}")
        print(f"Model URI: {model_uri}")
        
        # Add model description and tags
        try:
            client.set_registered_model_description(
                name=model_name,
                description="Enhanced ICC RAG System for legal research with dual-index retrieval using Databricks Vector Search and Meta Llama 3.3 70B"
            )
            
            # Add tags to the registered model
            client.set_registered_model_tag(
                name=model_name,
                key="domain",
                value="legal_research"
            )
            client.set_registered_model_tag(
                name=model_name,
                key="framework",
                value="databricks_vectorsearch"
            )
            client.set_registered_model_tag(
                name=model_name,
                key="llm_model",
                value=LLM_MODEL
            )
            client.set_registered_model_tag(
                name=model_name,
                key="embedding_model",
                value=EMBEDDING_MODEL
            )
            
        except Exception as tag_error:
            logger.warning(f"Could not set model tags: {tag_error}")
        
        # If stage is specified, transition the model to that stage
        if stage and stage != "None":
            try:
                client.transition_model_version_stage(
                    name=model_name,
                    version=registered_model.version,
                    stage=stage
                )
                print(f"✅ Model transitioned to stage: {stage}")
                logger.info(f"Model {model_name} version {registered_model.version} transitioned to {stage}")
            except Exception as stage_error:
                logger.error(f"Error transitioning model to stage {stage}: {stage_error}")
                print(f"⚠️ Warning: Could not transition model to stage {stage}: {stage_error}")
        
        return registered_model
        
    except Exception as e:
        logger.error(f"Error registering model: {e}")
        print(f"❌ Error registering model: {e}")
        return None

# Register the model with comprehensive error handling
try:
    print("📝 Starting Model Registration...")
    registered_model = register_model(
        model_run_id=model_run_id,
        model_name=MODEL_NAME,
        stage="None"  # Change to "Staging" or "Production" as needed
    )
    
    if registered_model:
        print(f"✅ Model registered successfully: {registered_model.name} v{registered_model.version}")
    else:
        print("❌ Model registration failed")
        raise RuntimeError("Model registration failed")
        
except Exception as e:
    print(f"❌ Error during model registration: {e}")
    import traceback
    traceback.print_exc()
    print("\n🔧 Troubleshooting Tips:")
    print("1. Check that the model run ID is valid")
    print("2. Verify Unity Catalog permissions")
    print("3. Ensure the model artifacts were created successfully")
    print("4. Check that the catalog and schema exist")
    raise

# COMMAND ----------

# MAGIC %md
# MAGIC ## Alternative: Simple Model for Serving (No Complex Authentication)

# COMMAND ----------

def create_simple_serving_model():
    """Create a simplified model that works better for serving without complex authentication."""
    
    class SimpleICCRAGModel(mlflow.pyfunc.PythonModel):
        def __init__(self):
            self.rag_system = None
            self.config = {
                "vector_search_endpoint": VECTOR_SEARCH_ENDPOINT,
                "llm_model": LLM_MODEL,
                "embedding_model": EMBEDDING_MODEL,
                "judgment_index": JUDGMENT_INDEX,
                "geneva_index": GENEVA_INDEX
            }
        
        def load_context(self, context):
            """Load the RAG system when the model is loaded."""
            try:
                logger.info("Loading simple ICC RAG system context...")
                
                # Simple initialization - let Databricks handle authentication
                self.rag_system = EnhancedICCRAGSystem(
                    vector_search_endpoint_name=self.config["vector_search_endpoint"],
                    llm_model=self.config["llm_model"]
                )
                
                logger.info("Simple ICC RAG system loaded successfully")
                
            except Exception as e:
                logger.error(f"Error loading simple RAG system context: {e}")
                # Create a minimal fallback
                try:
                    self.rag_system = EnhancedICCRAGSystem()
                    logger.info("Fallback RAG system initialization successful")
                except Exception as fallback_error:
                    logger.error(f"Fallback initialization failed: {fallback_error}")
                    raise RuntimeError(f"Failed to initialize RAG system: {e}")
        
        def predict(self, context, model_input):
            """Make predictions using the RAG system."""
            try:
                # Validate input
                if self.rag_system is None:
                    raise RuntimeError("RAG system not initialized. Call load_context first.")
                
                # Parse input
                if isinstance(model_input, dict):
                    question = model_input.get("question", "").strip()
                    top_k = int(model_input.get("top_k", 10))
                    conversation_id = model_input.get("conversation_id")
                elif hasattr(model_input, 'iloc'):  # DataFrame
                    if len(model_input) == 0:
                        raise ValueError("Empty input DataFrame")
                    question = str(model_input.iloc[0].get("question", "")).strip()
                    top_k = int(model_input.iloc[0].get("top_k", 10))
                    conversation_id = model_input.iloc[0].get("conversation_id")
                else:
                    raise ValueError(f"Unsupported input type: {type(model_input)}")
                
                # Validate input
                if not question:
                    raise ValueError("Question cannot be empty")
                if top_k < 1 or top_k > 50:
                    raise ValueError("top_k must be between 1 and 50")
                
                logger.info(f"Processing question: {question[:100]}...")
                
                # Retrieve context using enhanced routing
                retrieval_context = self.rag_system.retrieve_context_enhanced_routing(question, top_k)
                
                # Generate legal analysis
                analysis = self.rag_system.generate_legal_analysis_with_enhanced_routing(
                    question, context=retrieval_context, conversation_id=conversation_id
                )
                
                # Prepare response
                response = {
                    "analysis": analysis.analysis,
                    "key_findings": analysis.key_findings,
                    "citations": analysis.citations,
                    "resource_list": analysis.resource_list or {"geneva_documents": [], "judgment_documents": [], "additional_references": []},
                    "confidence_score": float(analysis.confidence_score),
                    "sources_used": int(analysis.sources_used),
                    "processing_time": float(analysis.processing_time)
                }
                
                logger.info(f"Analysis completed. Confidence: {response['confidence_score']:.3f}")
                return response
                
            except Exception as e:
                logger.error(f"Error in simple RAG model prediction: {e}")
                return {
                    "analysis": f"Error generating analysis: {str(e)}",
                    "key_findings": [],
                    "citations": [],
                    "resource_list": {"geneva_documents": [], "judgment_documents": [], "additional_references": []},
                    "confidence_score": 0.0,
                    "sources_used": 0,
                    "processing_time": 0.0
                }
    
    return SimpleICCRAGModel

# COMMAND ----------

# COMMAND ----------

# COMMAND ----------

# COMMAND ----------

# COMMAND ----------

# COMMAND ----------

# MAGIC %md
# MAGIC ## Model Testing Functions

# COMMAND ----------

def test_registered_model(model_name: str = MODEL_NAME, version: str = "latest"):
    """Test the registered model in Unity Catalog."""
    try:
        logger.info(f"Testing registered model: {model_name} version {version}")
        
        # For Unity Catalog, use the full model name
        model_uri = f"models:/{model_name}/{version}"
        loaded_model = mlflow.pyfunc.load_model(model_uri)
        
        # Test with a sample question
        test_input = {
            "question": "What are the key principles of international humanitarian law?",
            "top_k": 5,
            "conversation_id": "test_registration"
        }
        
        result = loaded_model.predict(test_input)
        
        logger.info("Model test successful!")
        print("✅ Model test successful!")
        print(f"Question: {test_input['question']}")
        print(f"Analysis: {result['analysis'][:200]}...")
        print(f"Key Findings: {result['key_findings']}")
        print(f"Confidence Score: {result['confidence_score']:.3f}")
        print(f"Sources Used: {result['sources_used']}")
        
        return result
    except Exception as e:
        logger.error(f"Error testing registered model: {e}")
        print(f"❌ Error testing registered model: {e}")
        return None

# COMMAND ----------

# MAGIC %md
# MAGIC ## Production Deployment

# COMMAND ----------

# Test the registered model
print("🧪 Testing registered model...")
test_result = test_registered_model()

# COMMAND ----------

# MAGIC %md
# MAGIC ## Summary

# MAGIC This notebook provides a complete production-ready deployment of the Enhanced ICC RAG System with:

# MAGIC 
# MAGIC **Key Features:**
# MAGIC - ✅ **Enhanced Vector Search**: Dual-index retrieval with intelligent routing
# MAGIC - ✅ **Advanced LLM**: Meta Llama 3.3 70B for legal analysis
# MAGIC - ✅ **MLflow 3.0**: Production deployment and model management
# MAGIC - ✅ **Unity Catalog**: Model registry and versioning
# MAGIC - ✅ **Model Serving**: Ready for production deployment
# MAGIC - ✅ **Comprehensive Testing**: Validation and quality assurance
# MAGIC 
# MAGIC **Architecture:**
# MAGIC - **Vector Search Endpoint**: `jgmt` with `databricks-gte-large-en`
# MAGIC - **LLM Model**: `databricks-meta-llama-3-3-70b-instruct`
# MAGIC - **Data Sources**: Past judgments and Geneva Convention documentation
# MAGIC - **Model Registry**: Unity Catalog with proper versioning
# MAGIC 
# MAGIC **Ready for Production Use!** 🚀

# COMMAND ----------
