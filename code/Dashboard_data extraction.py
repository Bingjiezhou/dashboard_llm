import time
import json
import os

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service as ChromeService
from webdriver_manager.chrome import ChromeDriverManager
from urllib.parse import urlparse, urljoin

# For HTML parsing
from bs4 import BeautifulSoup

#when websdriver not working:
# rm -rf /Users/bzhou01/.wdm/drivers/chromedriver
# pip install webdriver-manager



# -- Utility Functions for HTML Extraction --
def extract_structural_elements(soup):
    """
    Extract structural elements like headers (h1-h6) and paragraphs (p), excluding empty texts.
    """
    structure = {
        "headers": [],
        "paragraphs": [],
    }

    # Extract Headers (h1 to h6)
    for level in range(1, 7):
        for header in soup.find_all(f'h{level}'):
            text = header.get_text(strip=True)
            if text:  # Only include headers with non-empty text
                structure["headers"].append({
                    "level": level,
                    "text": text,
                })

    # Extract Paragraphs
    for p in soup.find_all('p'):
        text = p.get_text(strip=True)
        if text:  # Only include paragraphs with non-empty text
            structure["paragraphs"].append({
                "text": text,
            })

    return structure

def extract_div_hierarchy(soup):
    """
    Extract text from <div> elements that do not contain other <div> elements.
    """
    leaf_divs = []
    for div in soup.find_all('div'):
        # Check if this div contains any other divs
        if not div.find('div'):
            text = div.get_text(strip=True)
            if text:  # Only include divs with non-empty text
                div_info = {
                    "text": text
                }
                leaf_divs.append(div_info)
    return leaf_divs

def extract_a_tags(soup):
    """
    Extract all <a> tags with their text and href attribute (if present).
    """
    a_tags = []
    for a in soup.find_all('a'):
        text = a.get_text(strip=True)
        href = a.get('href', '')
        # Optionally filter out empty text, or empty href if you’d like
        if text or href:
            a_info = {
                "text": text,
                "href": href
            }
            a_tags.append(a_info)
    return a_tags

def extract_leaflet_paths(soup):
    """
    Extract all <path> tags that appear to be part of a Leaflet interactive map.
    Returns a list of dictionaries with the relevant attributes.
    """
    path_tags = []
    
    # Find <path> elements with the "leaflet-interactive" class (or any other specific criteria you need).
    for path_tag in soup.find_all('path', class_='leaflet-interactive'):
        # Gather attributes of interest from the path tag
        path_info = {}
        
        # You can add or remove attributes as needed
        attributes_of_interest = [
            "class",
            "stroke",
            "stroke-opacity",
            "stroke-width",
            "stroke-linecap",
            "stroke-linejoin",
            "fill",
            "fill-opacity",
            "fill-rule",
            "d"  # the crucial 'd' attribute for SVG paths
        ]
        
        for attr in attributes_of_interest:
            if path_tag.has_attr(attr):
                path_info[attr] = path_tag[attr]
        
        # Optionally, skip if no relevant attributes were found
        if path_info:
            path_tags.append(path_info)
    
    return path_tags

def extract_content_text(soup):
    """
    1. Parse the HTML with BeautifulSoup.
    2. Find the 'div' with class 'content'.
    3. Extract text from all child elements, 
       treating <br> as line breaks.
    """

    content_div = soup.find("div", class_="content")
    if not content_div:
        return ""  # or None, if you prefer
    
    # The get_text method automatically extracts text from child tags
    # Using separator='\n' will insert a newline wherever there is a <br> or block element
    text = content_div.get_text(separator="\n", strip=True)
    return text


def extract_page_data(driver, link):
    """
    Given a Selenium driver on a page, extract the desired HTML data and return as a dictionary.
    """
    html_content = driver.page_source
    soup = BeautifulSoup(html_content, 'lxml')

    structural_elements = extract_structural_elements(soup)
    divs = extract_div_hierarchy(soup)
    anchors = extract_a_tags(soup)
    map = extract_leaflet_paths(soup)
    otherinfo = extract_content_text(soup)

    extracted_data = {
        "url": link,
        "structural_elements": structural_elements,
        "div_hierarchy": divs,
        "links": anchors,
        "map": map,
        "other infornation": otherinfo

    }
    return extracted_data

# -- Original Link Extraction Code --
def get_links(driver, base_domain):
    """
    Extract all unique links from the current page, limited to http/https or relative paths,
    and restricted to the same netloc as base_domain.
    """
    # Wait for at least one <a> tag (up to 10 seconds)
    WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.TAG_NAME, "a")))

    page_source = driver.page_source
    # We'll just do a quick parse to get <a> tags; you can also do this with BeautifulSoup
    from parsel import Selector
    selector = Selector(text=page_source)
    raw_links = selector.css("a::attr(href)").getall()

    valid_schemes = ["http", "https", ""]
    domain_netloc = urlparse(base_domain).netloc  # e.g., "example.com"

    # Current page's URL (to resolve relative paths)
    current_url = driver.current_url

    unique_links = set()
    for link in raw_links:
        parsed = urlparse(link)
        # If it's http(s) or relative
        if parsed.scheme in valid_schemes:
            absolute_link = urljoin(current_url, link)
            link_parsed = urlparse(absolute_link)
            base_parsed = urlparse(base_domain) 
            # Restrict to our domain’s netloc
            if (link_parsed.netloc == domain_netloc
                and link_parsed.path.startswith(base_parsed.path)
                and link_parsed.fragment == ""):   #we remove fragment links with #:
                unique_links.add(absolute_link)

    return unique_links

# -- Modified Screenshot + Extraction Function --
def capture_full_page_screenshot_and_extract(driver, link, screenshot_filename, json_filename):
    """
    1. Navigates to `link`, waits for the page to load, closes pop-ups if present.
    2. Takes a full-page screenshot.
    3. Extracts structural elements, divs, anchors, etc. into JSON.
    4. Saves the JSON data to `json_filename`.
    """
    try:
        # 1. Reset the browser dimension to avoid carry-over from previous page
        driver.set_window_size(1920, 1080)
        driver.get(link)
        time.sleep(5)  # Allow time for the page to load

        # Attempt to close any pop-up (example logic)
        try:
            locator_popmake = (By.CSS_SELECTOR, "div#popmake-3700 button[aria-label='Close']")
            locator_modal   = (By.CSS_SELECTOR, "button.close[data-dismiss='modal'][aria-label='Close']")
            locator_ng      = (By.CSS_SELECTOR, "button[title='Close']")

            def presence_of_any_element_located(*locators):
                """Return the first element found among multiple locators, or False if none are found."""
                def _predicate(driver):
                    for loc in locators:
                        elements = driver.find_elements(*loc)
                        if elements:
                            return elements[0]  # Return the first match
                    return False
                return _predicate

            close_button = WebDriverWait(driver, 5).until(
                presence_of_any_element_located(locator_popmake, locator_modal, locator_ng)
            )
            driver.execute_script("arguments[0].click();", close_button)
            print("Pop-up closed successfully.")

        except Exception:
            pass  # Not critical if no pop-up found

        # Click on a blank space to dismiss floating elements
        try:
            driver.execute_script("""
                var event = new MouseEvent('click', {
                    bubbles: true,
                    cancelable: true,
                    view: window
                });
                document.elementFromPoint(10, 10).dispatchEvent(event);
            """)
        except Exception:
            pass

        # 2. Compute full-page dimensions
        width = driver.execute_script("return document.documentElement.scrollWidth")
        height = driver.execute_script("return document.documentElement.scrollHeight") + 200
        offset_height = driver.execute_script("return document.documentElement.offsetHeight")

        if width == 0 or height == 0 or offset_height == 0:
            # Fallback if dimension detection fails
            width, height = 3000, 3500
            driver.execute_script("""
                document.body.style.height = 'auto';
                document.body.style.minHeight = '3500px';
                document.documentElement.style.height = 'auto';
                document.documentElement.style.minHeight = '3500px';
            """)

        driver.set_window_size(width, height)
        time.sleep(2)

        # 3. Take screenshot
        html_element = driver.find_element(By.TAG_NAME, "html")
        html_element.screenshot(screenshot_filename)
        print(f"Screenshot saved as '{screenshot_filename}' for link: {link}")

        # 4. Extract HTML data
        extracted_data = extract_page_data(driver, link)

        # 5. Save the extracted data to JSON
        with open(json_filename, 'w', encoding='utf-8') as f:
            json.dump(extracted_data, f, indent=2, ensure_ascii=False)
        print(f"JSON data saved as '{json_filename}' for link: {link}")

    except Exception as e:
        print(f"Error processing {link}: {e}")

# -- Main --
def main():
    # 1. Specify your desired folder
    # os.makedirs('dashboard_1_Foodsystem', exist_ok=True)
    # output_folder = "dashboard_1_Foodsystem"
    # base_domain = "https://www.foodsystemsdashboard.org/"

    os.makedirs('dashboard_2_Fortification_new', exist_ok=True)
    output_folder = "dashboard_2_Fortification_new"
    base_domain = "https://fortificationdata.org/"
    start_domain ="https://fortificationdata.org/visualizations/"

    # os.makedirs('dashboard_3_FAO_consumption', exist_ok=True)
    # output_folder = "dashboard_3_FAO_consumption"
    # base_domain = "https://www.fao.org/gift-individual-food-consumption"
    
    # os.makedirs('dashboard_4_state_malnutrition_new', exist_ok=True)
    # output_folder = "dashboard_4_state_malnutrition_new"
    # base_domain = "https://acutemalnutrition.org/"

    # os.makedirs('dashboard_5_hungermap', exist_ok=True)
    # output_folder = "dashboard_5_hungermap"
    # base_domain = "https://hungermap.wfp.org/"

    # os.makedirs('dashboard_6_landscape', exist_ok=True)
    # output_folder = "dashboard_6_landscape"
    # base_domain = "https://www.who.int/data/nutrition/nlis/"


    # os.makedirs('dashboard_7_target_tracking', exist_ok=True)
    # output_folder = "dashboard_7_target_tracking"
    # base_domain = "https://www.who.int/data/nutrition/tracking-tool"


# human detection, not be able to access
    # os.makedirs('dashboard_8_vitA_unicef', exist_ok=True)
    # output_folder = "dashboard_8_vitA_unicef"
    # base_domain = "https://data.unicef.org/resources/vitamin-supplementation-interactive-dashboard-2/"

    # os.makedirs('dashboard_9_children_unicef', exist_ok=True)
    # output_folder = "dashboard_9_children_unicef"
    # base_domain = "https://data.unicef.org/resources/sowc-2019-statistical-tables-and-interactive-dashboard/"

    

    #start_url = base_domain
    start_url = start_domain

    options = Options()
    # Uncomment if you want to hide the browser
    options.add_argument("--headless")
    options.add_argument("--window-size=1920,1080")

    driver = webdriver.Chrome(
        service=ChromeService(ChromeDriverManager().install()),
        options=options
    )

    try:
        print(f"Starting URL: {start_url}")
        driver.get(start_url)
        time.sleep(15)  # Wait for page load

        # 1. Collect first-layer links from the start page
        first_layer_links = get_links(driver, base_domain)
        print(f"First-layer links found: {len(first_layer_links)}")
        first_layer_links_with_base = {start_url}.union(first_layer_links)

        first_layer_links_with_base_file = os.path.join(output_folder, "first_layer_links.json")
        with open(first_layer_links_with_base_file, "w", encoding="utf-8") as f:
            json.dump(list(first_layer_links_with_base), f, indent=2, ensure_ascii=False)
        print(f"First-layer links saved to {first_layer_links_with_base_file}")


        # # 2. For each first-layer link, collect second-layer links
        # second_layer_links = set()
        # for link in first_layer_links:
        #     try:
        #         driver.get(link)
        #         time.sleep(3)
        #         new_links = get_links(driver, base_domain)
        #         second_layer_links.update(new_links)
        #     except Exception as e:
        #         print(f"Error visiting {link}: {e}")

        # # 3. Combine links
        # all_links = first_layer_links.union(second_layer_links)
        # print(f"Total unique links (first + second): {len(all_links)}\n")

        # 4. For each link, take a screenshot and extract HTML data into JSON
        screenshot_count = 0
        for link in first_layer_links_with_base:
            screenshot_count += 1
            screenshot_filename =  os.path.join(output_folder,f"screenshot_{screenshot_count}.png")
            json_filename =  os.path.join(output_folder,f"html_section_{screenshot_count}.json")

            capture_full_page_screenshot_and_extract(
                driver,
                link,
                screenshot_filename,
                json_filename
            )

    finally:
        driver.quit()
        print("\nBrowser closed.")


if __name__ == "__main__":
    main()
