

from tools.web_search import web_search
from tools.calculator import calculator
from tools.edgar import get_filing, query_filing_documents
from tools.market import get_company_fundamentals, get_company_price_history, get_company_financials
from tools.kb import lookup_knowledge_base
from tools.wikipedia_search import search_wikipedia


TOOLS = [
            web_search,
           calculator,
          get_filing,
       query_filing_documents,
     get_company_fundamentals,
     get_company_price_history,
     get_company_financials,
             lookup_knowledge_base,
        search_wikipedia,
]
 