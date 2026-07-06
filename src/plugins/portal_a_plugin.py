from src.interfaces.portal_plugin import PortalPlugin
from src.models import IntimacaoRecord, Advogado, PortalType
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from typing import Dict, Any, List
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

class PortalAPlugin(PortalPlugin):
    """
    Plugin de demonstração usando Books to Scrape (http://books.toscrape.com/).
    Simula um portal de intimações onde cada livro é uma "intimação".
    """

    @property
    def portal_type(self) -> PortalType:
        return PortalType.PORTAL_A

    @property
    def portal_name(self) -> str:
        return "Books to Scrape"

    def __init__(self, headless: bool = True, remote_url: str | None = None):
        self.headless = headless
        self.remote_url = remote_url
        self.driver = None
        self._authenticated = False
        self.logger = logger

    async def authenticate(self, advogado: Advogado, config: Dict) -> bool:
        """Acessa a página principal (não requer login)."""
        if self.driver is None:
            from selenium import webdriver
            from selenium.webdriver.chrome.options import Options

            opts = Options()
            if self.headless:
                opts.add_argument("--headless=new")
                opts.add_argument("--no-sandbox")
                opts.add_argument("--disable-dev-shm-usage")
            opts.add_argument("--window-size=1366,768")
            opts.add_experimental_option("excludeSwitches", ["enable-automation"])

            if self.remote_url:
                self.driver = webdriver.Remote(
                    command_executor=self.remote_url, options=opts
                )
            else:
                self.driver = webdriver.Chrome(options=opts)

        self.driver.get("http://books.toscrape.com/")

        WebDriverWait(self.driver, 15).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "article.product_pod"))
        )

        self._authenticated = True
        self.logger.info("✅ Books to Scrape carregado com sucesso.")
        return True

    async def fetch_intimations(self, advogado: Advogado, data_referencia: str) -> List[Dict[str, Any]]:
        if not self._authenticated:
            await self.authenticate(advogado, {})

        raw = []
        try:
            books = self.driver.find_elements(By.CSS_SELECTOR, "article.product_pod")

            for i, book in enumerate(books):
                titulo_elem = book.find_element(By.CSS_SELECTOR, "h3 a")
                titulo = titulo_elem.get_attribute("title")
                preco_elem = book.find_element(By.CSS_SELECTOR, "p.price_color")
                preco = preco_elem.text
                star_elem = book.find_element(By.CSS_SELECTOR, "p.star-rating")
                star_class = star_elem.get_attribute("class")
                rating = star_class.replace("star-rating ", "")
                link = titulo_elem.get_attribute("href")

                raw.append({
                    "numero_processo": f"BOOK-{i+1:04d}",
                    "data": datetime.now().strftime("%d/%m/%Y"),
                    "objeto": f"{titulo} - Avaliação: {rating} estrelas - Preço: {preco}",
                    "link": link,
                    "preco": preco,
                    "rating": rating
                })

            self.logger.info(f"📚 Extraídos {len(raw)} livros da página.")
            return raw

        except Exception as e:
            self.logger.error(f"Erro ao extrair livros: {e}")
            return []

    async def process_intimation(self, raw_data: Dict[str, Any], advogado: Advogado) -> IntimacaoRecord:
        return IntimacaoRecord(
            data_consulta=datetime.now().strftime("%Y-%m-%d"),
            portal=self.portal_type.value,
            advogado=advogado.nome,
            sequencia=raw_data.get("numero_processo", "").split("-")[1],
            numero_processo=raw_data.get("numero_processo", ""),
            objeto_comunicacao=raw_data.get("objeto", ""),
            data_comunicacao=raw_data.get("data", ""),
            tipo_comunicacao=raw_data.get("rating", ""),
            raw_data=raw_data,
            status_registro="Pendente"
        )

    async def take_action(self, record: IntimacaoRecord, advogado: Advogado) -> None:
        self.logger.info(f"📖 Ação simulada para: {record.numero_processo}")

    async def cleanup(self) -> None:
        """Fecha o driver."""
        if self.driver:
            self.driver.quit()
            self.driver = None
            self._authenticated = False
            self.logger.info("Driver encerrado.")