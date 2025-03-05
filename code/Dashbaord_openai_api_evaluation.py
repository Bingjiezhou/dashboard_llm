import os
import re
import json
import base64
import openai


openai.api_key = "your API Key"


def evaluate_dashboard(
    criteria_file="criteria.json",
    screenshots_folder="path/to/screenshots",
    htnl_folder="path/to/htnl_sections",
    model_name="gpt-4o-mini",
    output_file="evaluation_results.txt"
):
    """
    1) Reads evaluation criteria from the given JSON file.
    2) Builds the system message with the 4-E principle description + criteria list.
    3) Pairs each screenshot_<i> with htnl_section_<i> (if both exist).
    4) Sends them to the GPT API in a single chat call (system + user messages).
    """

    # ----------------------------------------------------------------------
    #  STEP 1: Load the evaluation criteria from criteria.json
    # ----------------------------------------------------------------------
    with open(criteria_file, "r", encoding="utf-8") as file:
        criteria_data = json.load(file)
    criteria_list = criteria_data["criteria"]  # e.g. a list of criterion strings

    # Format the criteria into a bulleted/numbered list
    formatted_criteria = "\n".join(
        [f"{i}. {criterion}" for i, criterion in enumerate(criteria_list, start=1)]
    )

    # ----------------------------------------------------------------------
    #  STEP 2: Create the system message (the "role":"system")
    # ----------------------------------------------------------------------
    # It includes the 4-E principle, knowledge-graph explanation, and the loaded criteria
    system_content = f"""
You are an expert evaluator of nutrition and health dashboards. 
Based on the definition, knowledge graph, and detailed criteria, evaluate the dashboard screenshot and html extraction data we provide to you.

These criteria of evaluating dashboards are hierarchical, guided by a 4 E - principle:

1. Evidence:
   A logical path, context, underlying concepts, or results that form a graph should rest on solid evidence and facts. 
   A graph should be created with a well-thought-out description to establish credibility. 
   Are data timely, representative, reliable, and relevant?

2. Efficiency:
   A graph should help explain results/concepts by taking advantage of visual perception. 
   This calls for a deeper understanding of human perception and related cognitive load. 
   Are visuals intuitive and easily absorbed?

3. Emphasis:
   A graph should be created with cognizance of the intended audience, prompting viewers to notice the unexpected, 
   motivating questions and clarifying statements, and respecting the audience. 
   Are visuals clearly communicating their purpose, impact, or future actions?

4. Ethics:
   A graph should promote accuracy, precision, reliability, integrity, and inclusiveness 
   but remain balanced (neither excess nor deficiency). 
   Are visuals created with awareness of invoked empathy and inclusiveness?

The 4-E principle also supports a knowledge graph:
 - The data and documentation in the dashboard support the Evidence.
 - Data produces the visualization.
 - The visualization in the dashboard improves Efficiency.
 - The visualization and its narratives in the dashboard highlight Emphasis.
 - Proper documentation, accurate data, and visualization (together with supported links, videos, etc.) ensure Ethics.

Below is the **detailed set of criteria** generated under the 4-E principle (and a knowledge graph):
{formatted_criteria}
    """.strip()

    # ----------------------------------------------------------------------
    #  STEP 3: Gather and pair screenshots + corresponding JSON
    # ----------------------------------------------------------------------

    # Regex helper to extract the numeric index from filenames: screenshot_<i>.* or htnl_section_<i>.json
    def extract_index(filename, prefix):
        """
        e.g. if prefix='screenshot', match 'screenshot_12.jpg' -> index=12
             if prefix='htnl_section', match 'htnl_section_12.json' -> index=12
        """
        pattern = rf"^{prefix}_(\d+)\."
        match = re.search(pattern, filename)
        return int(match.group(1)) if match else None

    # Prepare dictionaries: { index -> path }
    screenshots_dict = {}
    for fname in os.listdir(screenshots_folder):
        if fname.lower().startswith("screenshot_"):
            idx = extract_index(fname, "screenshot")
            if idx is not None:
                screenshots_dict[idx] = os.path.join(screenshots_folder, fname)

    htnl_dict = {}
    for fname in os.listdir(htnl_folder):
        if fname.lower().startswith("htnl_section_") and fname.lower().endswith(".json"):
            idx = extract_index(fname, "htnl_section")
            if idx is not None:
                htnl_dict[idx] = os.path.join(htnl_folder, fname)

    # ----------------------------------------------------------------------
    #  STEP 4: Build the user message
    # ----------------------------------------------------------------------
    # We'll mimic your prior approach of using a list of "blocks" with type "text" or "image_url".
    #  => The final structure is used as the 'content' for the user role.
    #     If you have a custom approach that sends a list-of-dicts to the API, keep it as is;
    #     if your environment requires pure string content, adapt accordingly.
    user_message_content = []

    # Start with an introductory text block
    user_message_content.append(
        {
            "type": "text",
            "text": "Below you will find a series of dashboard screenshots (Please be aware that the screenshot is just a snapshot of page, which could be just showing part of the entire data when select a filter), each followed by its corresponding HTML extraction data for a dashboard. Please read and comprehend all as a whole as a dashboard. Please apply the above criteria in your evaluation. Evaluate the dashboard based on the following detailed set of criteria guided by 4-E principles. For each criterion in the detailed set of criteria, provide:1. A score from 1 to 10 (Scores 1-4 → Needs significant improvement (poor usability, unclear insights, or major issues);Scores 5-6 → Acceptable but with noticeable limitations (functional but not optimal).;Scores 7-8 → Good to very good (effective but can be further improved);Scores 9-10 → Excellent to industry-leading (best practices in dashboard quality)), each score should be ojective based on the content and a justification is needed. 2. A comprehensive, solide and justification for the above score, and you have to try to refer to the deails in certain screenshot or html file to provide evidence to support your justification. Maintain a professional tone and avoid overly positive or flattering language. Focus on being objective and critical and point out both strengths and weaknesses, and ensure the analysis includes any potential flaws, gaps, or issues. Make sure to evaluate by and provide score for all the 45 criteria"
        }
    )

    # Helper function to encode an image as base64
    def encode_image(image_path):
        with open(image_path, "rb") as img_file:
            return base64.b64encode(img_file.read()).decode("utf-8")

    # Sort all indices so we send them in ascending order
    all_indices = sorted(set(screenshots_dict.keys()) | set(htnl_dict.keys()))

    for i in all_indices:
        # 1) Add the screenshot (if present) for index i
        if i in screenshots_dict:
            screenshot_base64 = encode_image(screenshots_dict[i])
            user_message_content.append(
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/jpeg;base64,{screenshot_base64}"
                    }
                }
            )

        # 2) Add the corresponding HTML extraction JSON (if present)
        if i in htnl_dict:
            with open(htnl_dict[i], "r", encoding="utf-8") as json_file:
                data = json.load(json_file)
            # Convert to a pretty-printed string
            data_str = json.dumps(data, indent=2)
            user_message_content.append(
                {
                    "type": "text",
                    "text": f"Contents of html_section_{i}.json:\n{data_str}"
                }
            )

    # ----------------------------------------------------------------------
    #  STEP 5: Send the ChatCompletion request with system + user messages
    # ----------------------------------------------------------------------
    response = openai.chat.completions.create(
        model=model_name,
        seed =123,
        temperature = 0,
        messages=[
            {
                "role": "system",
                "content": system_content
            },
            {
                "role": "user",
                "content": user_message_content  # list of dict blocks
            }
        ]
    )

    # ----------------------------------------------------------------------
    #  STEP 6: Save the assistant's reply to a file
    # ----------------------------------------------------------------------
    assistant_reply = response.choices[0].message.content
    with open(output_file, "w", encoding="utf-8") as out_file:
        out_file.write(assistant_reply)


# Example usage (adjust paths, etc.):


    # ----------------------------------------------------------------------
    #  all files - 4o model
    # ----------------------------------------------------------------------

if __name__ == "__main__":
    evaluate_dashboard(
        criteria_file="criteria.json",
        screenshots_folder="/Users/bzhou01/Library/CloudStorage/Box-Box/BingjieProjects/LLMs_Dashboards/selenium/dashboard_extracted/dashboard_1_Foodsystem",
        htnl_folder="/Users/bzhou01/Library/CloudStorage/Box-Box/BingjieProjects/LLMs_Dashboards/selenium/dashboard_extracted/dashboard_1_Foodsystem",
        model_name="gpt-4o-2024-11-20",
        output_file="openai_api_evaluation/dashboard_1_Foodsystem-4o-latest.txt"
    )

if __name__ == "__main__":
    evaluate_dashboard(
        criteria_file="criteria.json",
        screenshots_folder="/Users/bzhou01/Library/CloudStorage/Box-Box/BingjieProjects/LLMs_Dashboards/selenium/dashboard_extracted/dashboard_2_Fortification",
        htnl_folder="/Users/bzhou01/Library/CloudStorage/Box-Box/BingjieProjects/LLMs_Dashboards/selenium/dashboard_extracted/dashboard_2_Fortification",
        model_name="gpt-4o-2024-11-20",
        output_file="openai_api_evaluation/dashboard_2_Fortification-4o-latest.txt"
    )

if __name__ == "__main__":
    evaluate_dashboard(
        criteria_file="criteria.json",
        screenshots_folder="/Users/bzhou01/Library/CloudStorage/Box-Box/BingjieProjects/LLMs_Dashboards/selenium/dashboard_extracted/dashboard_3_FAO_consumption",
        htnl_folder="/Users/bzhou01/Library/CloudStorage/Box-Box/BingjieProjects/LLMs_Dashboards/selenium/dashboard_extracted/dashboard_3_FAO_consumption",
        model_name="gpt-4o-2024-11-20",
        output_file="openai_api_evaluation/dashboard_3_FAO_consumption-4o-latest.txt"
    )


if __name__ == "__main__":
    evaluate_dashboard(
        criteria_file="criteria.json",
        screenshots_folder="/Users/bzhou01/Library/CloudStorage/Box-Box/BingjieProjects/LLMs_Dashboards/selenium/dashboard_extracted/dashboard_4_state_malnutrition",
        htnl_folder="/Users/bzhou01/Library/CloudStorage/Box-Box/BingjieProjects/LLMs_Dashboards/selenium/dashboard_extracted/dashboard_4_state_malnutrition",
        model_name="gpt-4o-2024-11-20",
        output_file="openai_api_evaluation/dashboard_4_state_malnutrition-4o-latest.txt"
    )


if __name__ == "__main__":
    evaluate_dashboard(
        criteria_file="criteria.json",
        screenshots_folder="/Users/bzhou01/Library/CloudStorage/Box-Box/BingjieProjects/LLMs_Dashboards/selenium/dashboard_extracted/dashboard_5_hungermap",
        htnl_folder="/Users/bzhou01/Library/CloudStorage/Box-Box/BingjieProjects/LLMs_Dashboards/selenium/dashboard_extracted/dashboard_5_hungermap",
        model_name="gpt-4o-2024-11-20",
        output_file="openai_api_evaluation/dashboard_5_hungermap-4o-latest.txt"
    )

if __name__ == "__main__":
    evaluate_dashboard(
        criteria_file="criteria.json",
        screenshots_folder="/Users/bzhou01/Library/CloudStorage/Box-Box/BingjieProjects/LLMs_Dashboards/selenium/dashboard_extracted/dashboard_6_landscape",
        htnl_folder="/Users/bzhou01/Library/CloudStorage/Box-Box/BingjieProjects/LLMs_Dashboards/selenium/dashboard_extracted/dashboard_6_landscape",
        model_name="gpt-4o-2024-11-20",
        output_file="openai_api_evaluation/dashboard_6_landscape-4o-latest.txt"
    )

if __name__ == "__main__":
    evaluate_dashboard(
        criteria_file="criteria.json",
        screenshots_folder="/Users/bzhou01/Library/CloudStorage/Box-Box/BingjieProjects/LLMs_Dashboards/selenium/dashboard_extracted/dashboard_7_target_tracking",
        htnl_folder="/Users/bzhou01/Library/CloudStorage/Box-Box/BingjieProjects/LLMs_Dashboards/selenium/dashboard_extracted/dashboard_7_target_tracking",
        model_name="gpt-4o-2024-11-20",
        output_file="openai_api_evaluation/dashboard_7_target_tracking-4o-latest.txt"
    )

    # ----------------------------------------------------------------------
    #  all files - 4o - MINI model
    # ----------------------------------------------------------------------

# if __name__ == "__main__":
#     evaluate_dashboard(
#         criteria_file="criteria.json",
#         screenshots_folder="/Users/bzhou01/Library/CloudStorage/Box-Box/BingjieProjects/LLMs_Dashboards/selenium/dashboard_extracted/dashboard_1_Foodsystem",
#         htnl_folder="/Users/bzhou01/Library/CloudStorage/Box-Box/BingjieProjects/LLMs_Dashboards/selenium/dashboard_extracted/dashboard_1_Foodsystem",
#         model_name="gpt-4o-mini",
#         output_file="openai_api_evaluation/dashboard_1_Foodsystem-4o-mini.txt"
#     )

# if __name__ == "__main__":
#     evaluate_dashboard(
#         criteria_file="criteria.json",
#         screenshots_folder="/Users/bzhou01/Library/CloudStorage/Box-Box/BingjieProjects/LLMs_Dashboards/selenium/dashboard_extracted/dashboard_2_Fortification",
#         htnl_folder="/Users/bzhou01/Library/CloudStorage/Box-Box/BingjieProjects/LLMs_Dashboards/selenium/dashboard_extracted/dashboard_2_Fortification",
#         model_name="gpt-4o-mini",
#         output_file="openai_api_evaluation/dashboard_2_Fortification-4o-mini.txt"
#     )

# if __name__ == "__main__":
#     evaluate_dashboard(
#         criteria_file="criteria.json",
#         screenshots_folder="/Users/bzhou01/Library/CloudStorage/Box-Box/BingjieProjects/LLMs_Dashboards/selenium/dashboard_extracted/dashboard_3_FAO_consumption",
#         htnl_folder="/Users/bzhou01/Library/CloudStorage/Box-Box/BingjieProjects/LLMs_Dashboards/selenium/dashboard_extracted/dashboard_3_FAO_consumption",
#         model_name="gpt-4o-mini",
#         output_file="openai_api_evaluation/dashboard_3_FAO_consumption-4o-mini.txt"
#     )


# if __name__ == "__main__":
#     evaluate_dashboard(
#         criteria_file="criteria.json",
#         screenshots_folder="/Users/bzhou01/Library/CloudStorage/Box-Box/BingjieProjects/LLMs_Dashboards/selenium/dashboard_extracted/dashboard_4_state_malnutrition",
#         htnl_folder="/Users/bzhou01/Library/CloudStorage/Box-Box/BingjieProjects/LLMs_Dashboards/selenium/dashboard_extracted/dashboard_4_state_malnutrition",
#         model_name="gpt-4o-mini",
#         output_file="openai_api_evaluation/dashboard_4_state_malnutrition-4o-mini.txt"
#     )



# if __name__ == "__main__":
#     evaluate_dashboard(
#         criteria_file="criteria.json",
#         screenshots_folder="/Users/bzhou01/Library/CloudStorage/Box-Box/BingjieProjects/LLMs_Dashboards/selenium/dashboard_extracted/dashboard_5_hungermap",
#         htnl_folder="/Users/bzhou01/Library/CloudStorage/Box-Box/BingjieProjects/LLMs_Dashboards/selenium/dashboard_extracted/dashboard_5_hungermap",
#         model_name="gpt-4o-mini",
#         output_file="openai_api_evaluation/dashboard_5_hungermap-4o-mini.txt"
#     )

# if __name__ == "__main__":
#     evaluate_dashboard(
#         criteria_file="criteria.json",
#         screenshots_folder="/Users/bzhou01/Library/CloudStorage/Box-Box/BingjieProjects/LLMs_Dashboards/selenium/dashboard_extracted/dashboard_6_landscape",
#         htnl_folder="/Users/bzhou01/Library/CloudStorage/Box-Box/BingjieProjects/LLMs_Dashboards/selenium/dashboard_extracted/dashboard_6_landscape",
#         model_name="gpt-4o-mini",
#         output_file="openai_api_evaluation/dashboard_6_landscape-4o-mini.txt"
#     )

# if __name__ == "__main__":
#     evaluate_dashboard(
#         criteria_file="criteria.json",
#         screenshots_folder="/Users/bzhou01/Library/CloudStorage/Box-Box/BingjieProjects/LLMs_Dashboards/selenium/dashboard_extracted/dashboard_7_target_tracking",
#         htnl_folder="/Users/bzhou01/Library/CloudStorage/Box-Box/BingjieProjects/LLMs_Dashboards/selenium/dashboard_extracted/dashboard_7_target_tracking",
#         model_name="gpt-4o-mini",
#         output_file="openai_api_evaluation/dashboard_7_target_tracking-4o-mini.txt"
#     )


