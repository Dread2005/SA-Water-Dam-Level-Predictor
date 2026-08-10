import markdown
from weasyprint import HTML
import os

md_path = "/home/chiyedza/Downloads/Personal projects/SA-Water-Dam-Level-Predictor/Planning/Current_project.md"
pdf_path = "/home/chiyedza/Downloads/Personal projects/SA-Water-Dam-Level-Predictor/Planning/Current_project.pdf"

with open(md_path, 'r', encoding='utf-8') as f:
    md_text = f.read()

html = markdown.markdown(md_text, extensions=['tables', 'fenced_code'])
# Optionally add some basic CSS for better styling
html = f"""
<html>
<head>
<meta charset="utf-8">
<style>
body {{ font-family: DejaVu Sans, sans-serif; margin: 40px; }}
h1, h2, h3 {{ color: #2c3e50; }}
table {{ border-collapse: collapse; width: 100%; margin-bottom: 1em; }}
th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
th {{ background-color: #f2f2f2; }}
blockquote {{ border-left: 4px solid #ddd; padding-left: 1em; color: #555; }}
code {{ background-color: #f8f8f8; padding: 2px 4px; }}
pre {{ background-color: #f8f8f8; padding: 10px; overflow: auto; }}
</style>
</head>
<body>
{html}
</body>
</html>
"""

HTML(string=html).write_pdf(pdf_path)
print(f"PDF written to {pdf_path}")