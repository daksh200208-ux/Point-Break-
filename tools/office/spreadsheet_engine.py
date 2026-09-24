"""
Point Break Spreadsheet & Tabular Data Engine
=============================================
Provides automated operations on XLSX, CSV, and tabular datasets:
1. Creating and formatting spreadsheets.
2. Reading and filtering tabular records.
3. Calculating statistical summaries (sum, mean, group-by).
4. Generating chart images (bar, line, scatter, pie) using matplotlib.
"""

import os
import json
from typing import Dict, Any, List, Optional
import pandas as pd
import matplotlib
matplotlib.use("Agg") # Non-interactive headless backend
import matplotlib.pyplot as plt

from tools.registry import register_tool

class SpreadsheetEngine:
    def __init__(self):
        pass

    def create_spreadsheet(
        self,
        output_path: str,
        data: List[Dict[str, Any]],
        columns: Optional[List[str]] = None,
        sheet_name: str = "Data"
    ) -> Dict[str, Any]:
        """Creates a new CSV or XLSX file from structured data."""
        df = pd.DataFrame(data)
        if columns:
            existing = [c for c in columns if c in df.columns]
            if existing: df = df[existing]

        parent = os.path.dirname(output_path)
        if parent and not os.path.exists(parent):
            os.makedirs(parent, exist_ok=True)

        if output_path.lower().endswith(".xlsx"):
            df.to_excel(output_path, sheet_name=sheet_name, index=False)
        else:
            if not output_path.lower().endswith(".csv"):
                output_path += ".csv"
            df.to_csv(output_path, index=False)

        print(f"[SpreadsheetEngine] 📊 Generated spreadsheet at: {output_path} ({len(df)} rows)")
        return {
            "success": True,
            "path": output_path,
            "rows": len(df),
            "columns": list(df.columns)
        }

    def read_spreadsheet(self, file_path: str, limit: int = 50) -> Dict[str, Any]:
        """Reads tabular data from CSV or Excel file."""
        if not os.path.exists(file_path):
            return {"success": False, "error": f"File not found: {file_path}"}

        if file_path.lower().endswith((".xlsx", ".xls")):
            df = pd.read_excel(file_path)
        else:
            df = pd.read_csv(file_path)

        preview = df.head(limit).to_dict(orient="records")
        return {
            "success": True,
            "total_rows": len(df),
            "columns": list(df.columns),
            "data_preview": preview
        }

    def analyze_spreadsheet(self, file_path: str, group_by: Optional[str] = None, metric_col: Optional[str] = None) -> Dict[str, Any]:
        """Computes summary statistics and group aggregations."""
        if not os.path.exists(file_path):
            return {"success": False, "error": f"File not found: {file_path}"}

        df = pd.read_excel(file_path) if file_path.lower().endswith((".xlsx", ".xls")) else pd.read_csv(file_path)
        summary = {
            "row_count": len(df),
            "columns": list(df.columns),
            "numeric_stats": df.describe().to_dict()
        }

        if group_by and group_by in df.columns and metric_col and metric_col in df.columns:
            agg = df.groupby(group_by)[metric_col].agg(["sum", "mean", "count"]).reset_index()
            summary["aggregation"] = agg.to_dict(orient="records")

        return {"success": True, "analysis": summary}

    def generate_chart(
        self,
        file_path: str,
        x_col: str,
        y_col: str,
        chart_type: str = "bar",
        title: str = "Data Visualization",
        output_png: Optional[str] = None
    ) -> Dict[str, Any]:
        """Plots data from a spreadsheet and saves a high-res PNG chart."""
        if not os.path.exists(file_path):
            return {"success": False, "error": f"File not found: {file_path}"}

        df = pd.read_excel(file_path) if file_path.lower().endswith((".xlsx", ".xls")) else pd.read_csv(file_path)
        if x_col not in df.columns or y_col not in df.columns:
            return {"success": False, "error": f"Specified columns ('{x_col}', '{y_col}') not in dataframe"}

        if not output_png:
            output_png = os.path.splitext(file_path)[0] + "_chart.png"

        plt.figure(figsize=(10, 6), dpi=150)
        plt.style.use("ggplot")

        if chart_type.lower() == "line":
            plt.plot(df[x_col].astype(str), df[y_col], marker='o', linewidth=2, color="#3b82f6")
        elif chart_type.lower() == "pie":
            plt.pie(df[y_col], labels=df[x_col].astype(str), autopct='%1.1f%%', colors=plt.cm.Paired.colors)
        else: # Default bar
            plt.bar(df[x_col].astype(str), df[y_col], color="#2563eb", edgecolor="#1d4ed8")

        plt.title(title, fontsize=14, fontweight="bold", pad=15)
        plt.xlabel(x_col, fontsize=11)
        plt.ylabel(y_col, fontsize=11)
        plt.xticks(rotation=45, ha='right')
        plt.tight_layout()

        plt.savefig(output_png)
        plt.close()

        print(f"[SpreadsheetEngine] 📈 Generated chart at: {output_png}")
        return {"success": True, "chart_path": output_png, "type": chart_type}

spreadsheet_engine = SpreadsheetEngine()

@register_tool(name="create_spreadsheet", description="Creates a new CSV or XLSX spreadsheet", risk_level="R1")
def create_spreadsheet(output_path: str, data: List[Dict[str, Any]], columns: Optional[List[str]] = None, **kwargs) -> Dict[str, Any]:
    return spreadsheet_engine.create_spreadsheet(output_path, data, columns)

@register_tool(name="read_spreadsheet", description="Reads records from CSV or XLSX file", risk_level="R0")
def read_spreadsheet(file_path: str, limit: int = 50, **kwargs) -> Dict[str, Any]:
    return spreadsheet_engine.read_spreadsheet(file_path, limit)

@register_tool(name="analyze_spreadsheet", description="Calculates metrics and aggregations from spreadsheet", risk_level="R0")
def analyze_spreadsheet(file_path: str, group_by: Optional[str] = None, metric_col: Optional[str] = None, **kwargs) -> Dict[str, Any]:
    return spreadsheet_engine.analyze_spreadsheet(file_path, group_by, metric_col)

@register_tool(name="generate_chart", description="Generates a chart image (bar, line, pie) from spreadsheet", risk_level="R1")
def generate_chart(file_path: str, x_col: str, y_col: str, chart_type: str = "bar", title: str = "Chart", output_png: Optional[str] = None, **kwargs) -> Dict[str, Any]:
    return spreadsheet_engine.generate_chart(file_path, x_col, y_col, chart_type, title, output_png)
