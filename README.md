
# Procurement Dashboard – AM/NS India

A production-ready **Streamlit** dashboard app for the Procurement team to analyze **PRs** and **POs**, with **big KPI tiles** and **category-wise** insights across **MRO, Services, Capex, PCM**.

## ✨ Features
- Upload a single Excel with sheets: **PRs**, **POs**, optional **Category_Mapping**.
- **Column Mapper** to align your actual column names to expected fields.
- **Category logic precedence**: explicit `Category` → mapping sheet → in-app mapping editor.
- **Big KPI tiles:** Total PRs, Total POs, Open PRs, Open Delivery POs.
- Filters: date range, category, vendor, buyer, statuses.
- Charts: grouped bars (PRs & POs by category), donut shares, monthly trend lines.
- Detailed tables with export buttons (Excel).
- Data Health page: missing mappings, dtypes, mapping coverage.

## 🧩 Expected Fields (Flexible Mapping)
(…same as your spec…)

## ⚙️ Definitions (Configurable)
(…Open PRs & Open Delivery POs logic…)

## 🚀 Run Locally
```bash
pip install -r requirements.txt
streamlit run app.py
