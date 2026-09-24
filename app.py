import streamlit as st
import pandas as pd
import smtplib
import ssl
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.image import MIMEImage
import base64
from datetime import datetime, timedelta
import os
import json
import re
import requests
import time
from io import BytesIO
from PIL import Image

# ============================================================
# CONFIGURACIÓN
# ============================================================

SMTP_SERVER = "smtp.office365.com"
SMTP_PORT = 587

URL_LOGO_GITHUB = "https://raw.githubusercontent.com/Iamnotmanolotaco/Inmigration-USCIS-Alerts-Automation/main/image.png"
URL_BANNER_GITHUB = "https://raw.githubusercontent.com/Iamnotmanolotaco/Inmigration-USCIS-Alerts-Automation/main/banner.png"

DAYS_BEFORE = 10
DAYS_AFTER = 150
LOGO_WIDTH = 180

# ============================================================
# FUNCIONES PARA OBTENER Y REDIMENSIONAR LOGO
# ============================================================

def get_image_from_github(url):
    try:
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            return response.content
        else:
            return None
    except Exception as e:
        return None

def resize_logo(logo_bytes, target_width=LOGO_WIDTH):
    try:
        if logo_bytes is None:
            return None
        img = Image.open(BytesIO(logo_bytes))
        original_width, original_height = img.size
        aspect_ratio = original_height / original_width
        target_height = int(target_width * aspect_ratio)
        img_resized = img.resize((target_width, target_height), Image.Resampling.LANCZOS)
        output = BytesIO()
        img_resized.save(output, format='PNG', quality=95, optimize=True)
        output.seek(0)
        print(f"   🖼️ Logo redimensionado: {target_width}x{target_height}px")
        return output.getvalue()
    except Exception as e:
        print(f"   ⚠️ Error al redimensionar logo: {e}")
        return logo_bytes

def get_logo_bytes():
    logo_bytes = get_image_from_github(URL_LOGO_GITHUB)
    if logo_bytes:
        return resize_logo(logo_bytes, LOGO_WIDTH)
    return None

def get_banner_base64():
    image_bytes = get_image_from_github(URL_BANNER_GITHUB)
    if image_bytes:
        base64_string = base64.b64encode(image_bytes).decode('utf-8')
        return f"data:image/png;base64,{base64_string}"
    return None

# ============================================================
# FUNCIONES DE UTILIDAD
# ============================================================

def calcular_dias_hasta_deadline(deadline_str, fecha_referencia):
    if pd.isna(deadline_str) or deadline_str == "":
        return None
    try:
        if isinstance(deadline_str, (datetime, pd.Timestamp)):
            deadline_date = deadline_str.date()
        else:
            deadline_date = pd.to_datetime(deadline_str).date()
        return (deadline_date - fecha_referencia).days
    except:
        return None

def is_rfe_case(case_status):
    if pd.isna(case_status):
        return False
    rfe_patterns = [
        'RFE_RECEIVED', 'RFE_RESPONSE_SENT', 'RFE SENT',
        'RFE RECEIVED', 'RFE RESPONSE SENT', 'RFE_RESPONSE',
        'RFE PENDING', 'RFE ISSUED', 'RFE RESPONSE RECEIVED'
    ]
    status_str = str(case_status).strip().upper()
    for pattern in rfe_patterns:
        if pattern.upper().replace('_', ' ') in status_str or pattern in status_str:
            return True
    return False

def get_days_style(days):
    if days <= 0:
        return "days-critical", f"{abs(days)} days overdue"
    elif days <= 2:
        return "days-critical", f"{days} days"
    elif days <= 5:
        return "days-warning", f"{days} days"
    else:
        return "days-info", f"{days} days"

def get_team_email(team_name):
    team_emails = {
        "Alonso": "Legalassistant2@communitylawgroup.com",
        "Francy": "legalsupport11@communitylawgroup.com",
        "Kevin": "legalsupport12@communitylawgroup.com",
        "Juliana": "legalsupport4@communitylawgroup.com",
        "Kia": "kia@communitylawgroup.com",
    }
    return team_emails.get(team_name.strip(), None)

def get_cc_for_team(team_name):
    cc_by_team = {
        "Alonso": ["Legalassistant7@communitylawgroup.com","amanda@communitylawgroup.com","ellen@communitylawgroup.com","Delmin@communitylawgroup.com", "legalsupport7@communitylawgroup.com"],
        "Francy": ["legalsupport5@communitylawgroup.com","amanda@communitylawgroup.com","Delmin@communitylawgroup.com"],
        "Kevin": ["ellen@communitylawgroup.com","Delmin@communitylawgroup.com"],
        "Juliana": ["supernumerary2@communitylawgroup.com", "oscar@communitylawgroup.com", "Delmin@communitylawgroup.com"],
        "Kia": ["litigationdepartment@communitylawgroup.com"],
    }
    default_cc = ["default_supervisor@communitylawgroup.com"]
    return cc_by_team.get(team_name.strip(), default_cc)

# ============================================================
# FUNCIÓN PARA GENERAR HTML DEL CORREO CON LOGO (CID) - CORREGIDA
# ============================================================

def generar_html_correo(team_cases, team_name, fecha_referencia, logo_cid=None):
    # ============================================================
    # CORRECCIÓN: Usar apply() en lugar de iteración manual
    # Esto evita el error "iloc cannot enlarge its target object"
    # ============================================================
    if 'Case Status' in team_cases.columns:
        is_rfe = team_cases['Case Status'].apply(is_rfe_case)
    else:
        is_rfe = pd.Series([False] * len(team_cases), index=team_cases.index)
    
    team_cases_filtered = team_cases[~is_rfe].copy()
    if len(team_cases_filtered) == 0:
        return None
    
    team_cases_filtered['Days_Until'] = team_cases_filtered['Deadline'].apply(
        lambda x: calcular_dias_hasta_deadline(x, fecha_referencia)
    )
    
    overdue = team_cases_filtered[team_cases_filtered['Days_Until'] < 0].sort_values('Days_Until')
    upcoming = team_cases_filtered[team_cases_filtered['Days_Until'] >= 0].sort_values('Days_Until')
    
    total_cases = len(team_cases_filtered)
    urgent_count = len(overdue)
    upcoming_count = len(upcoming)
    rfe_excluded = is_rfe.sum()
    
    logo_html = ""
    if logo_cid:
        logo_html = f"""
        <div class="footer-logo">
            <img src="cid:{logo_cid}" 
                 alt="Community Law Group" 
                 width="{LOGO_WIDTH}" 
                 style="width: {LOGO_WIDTH}px; height: auto; border: none; display: block; margin: 0 auto;">
        </div>
        """
    
    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <style>
            * {{ margin: 0; padding: 0; box-sizing: border-box; }}
            body {{ font-family: 'Segoe UI', Arial, sans-serif; background-color: #e8eef2; padding: 20px; }}
            .email-container {{ max-width: 1100px; margin: 0 auto; background-color: #ffffff; border-radius: 12px; overflow: hidden; box-shadow: 0 4px 20px rgba(0,0,0,0.1); }}
            .email-header {{ background-color: #f0f4f8; padding: 28px 36px; border-bottom: 2px solid #d0d8e4; }}
            .logo {{ font-size: 28px; font-weight: 700; color: #1a2a3a; }}
            .logo span {{ font-weight: 400; color: #3a5a7a; }}
            .report-subtitle {{ font-size: 15px; color: #3a5a7a; margin-top: 6px; }}
            .greeting {{ background-color: #f8fafc; padding: 24px 36px; border-bottom: 1px solid #e2e8f0; }}
            .greeting h2 {{ font-size: 20px; font-weight: 600; color: #1a2a3a; margin-bottom: 8px; }}
            .greeting p {{ font-size: 14px; color: #4a6a8a; }}
            .urgent-alert {{ background-color: #c0392b; color: #ffffff; padding: 16px 24px; margin: 20px 36px 0 36px; border-radius: 10px; display: flex; align-items: center; gap: 15px; flex-wrap: wrap; }}
            .urgent-alert-icon {{ font-size: 32px; font-weight: 700; }}
            .urgent-alert-text {{ flex: 1; }}
            .urgent-alert-text h3 {{ font-size: 18px; font-weight: 700; }}
            .urgent-count {{ background-color: rgba(255,255,255,0.25); padding: 6px 16px; border-radius: 30px; font-size: 24px; font-weight: 700; }}
            .report-info {{ padding: 18px 36px; background-color: #ffffff; border-bottom: 1px solid #e2e8f0; display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 12px; margin-top: 20px; }}
            .info-grid {{ display: flex; gap: 28px; flex-wrap: wrap; }}
            .info-label {{ font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.8px; color: #6a7e9e; }}
            .info-value {{ font-size: 14px; font-weight: 500; color: #1a2a3a; }}
            .recipient-badge {{ background-color: #1a3a5c; color: #ffffff; padding: 6px 16px; border-radius: 30px; font-size: 13px; font-weight: 600; }}
            .stats-title {{ padding: 20px 36px 0 36px; }}
            .stats-title h3 {{ font-size: 16px; font-weight: 600; color: #1a2a3a; border-bottom: 2px solid #e2e8f0; padding-bottom: 8px; }}
            .stats-container {{ padding: 0 36px 28px 36px; }}
            .stats-grid {{ display: flex; gap: 20px; flex-wrap: wrap; }}
            .stat-card {{ background-color: #f8fafc; padding: 22px 28px; border-radius: 12px; border: 1px solid #e2e8f0; min-width: 160px; }}
            .stat-number {{ font-size: 36px; font-weight: 700; }}
            .stat-label {{ font-size: 12px; font-weight: 600; color: #6a7e9e; text-transform: uppercase; }}
            .text-urgent {{ color: #c0392b; }}
            .text-warning {{ color: #e67e22; }}
            .table-section {{ margin: 28px 36px; }}
            .section-header {{ border-bottom: 2px solid #e2e8f0; padding-bottom: 10px; display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 10px; }}
            .section-title {{ font-size: 17px; font-weight: 700; color: #1a2a3a; }}
            .section-badge {{ background-color: #e8eef2; color: #3a5a7a; padding: 4px 12px; border-radius: 20px; font-size: 12px; font-weight: 600; }}
            .data-table {{ width: 100%; border-collapse: collapse; font-size: 13px; border: 1px solid #e2e8f0; border-radius: 10px; overflow: hidden; }}
            .data-table th {{ background-color: #f0f4f8; color: #1a2a3a; font-weight: 700; padding: 12px 14px; text-align: left; border-bottom: 2px solid #e2e8f0; }}
            .data-table td {{ padding: 12px 14px; border-bottom: 1px solid #eef2f6; color: #2a3a4a; }}
            .data-table tr:last-child td {{ border-bottom: none; }}
            .days-critical {{ color: #c0392b; background-color: #fee2e2; padding: 4px 12px; border-radius: 20px; font-weight: 700; }}
            .days-warning {{ color: #92400e; background-color: #fef3c7; padding: 4px 12px; border-radius: 20px; font-weight: 700; }}
            .days-info {{ color: #1e40af; background-color: #dbeafe; padding: 4px 12px; border-radius: 20px; font-weight: 700; }}
            .rfe-note {{ background-color: #fef3c7; border-left: 4px solid #e67e22; padding: 12px 20px; margin: 20px 36px; border-radius: 8px; font-size: 12px; color: #92400e; }}
            .email-footer {{ background-color: #f0f4f8; padding: 20px 36px; border-top: 1px solid #e2e8f0; text-align: center; margin-top: 20px; }}
            .footer-text {{ font-size: 11px; color: #6a7e9e; margin-bottom: 5px; }}
            .footer-note {{ font-size: 10px; color: #8a9eb8; }}
            .footer-logo {{
                margin: 10px 0 8px 0;
                text-align: center;
            }}
            .footer-logo img {{
                width: {LOGO_WIDTH}px !important;
                height: auto !important;
                max-width: {LOGO_WIDTH}px !important;
                border: none !important;
                display: block !important;
                margin: 0 auto !important;
            }}
            @media (max-width: 700px) {{
                .email-header, .greeting, .report-info, .stats-title, .stats-container, .table-section, .email-footer {{
                    padding-left: 20px; padding-right: 20px;
                }}
                .urgent-alert {{ margin-left: 20px; margin-right: 20px; }}
                .stats-grid {{ gap: 12px; }}
                .stat-card {{ padding: 16px 20px; min-width: 130px; }}
                .data-table th, .data-table td {{ padding: 8px 10px; font-size: 11px; }}
            }}
        </style>
    </head>
    <body>
        <div class="email-container">
            <div class="email-header">
                <div class="logo">LEGAL SUPPORT TEAM <span>ALERTING SYSTEM</span></div>
                <div class="report-subtitle">Deadline and Case Management System</div>
            </div>
            <div class="greeting">
                <h2>Hello, {team_name}</h2>
                <p>Below are the cases assigned to your team that require attention. Please review the information and take necessary actions.</p>
            </div>
    """
    
    if len(overdue) > 0:
        html += f"""
            <div class="urgent-alert">
                <div class="urgent-alert-icon">⚠️</div>
                <div class="urgent-alert-text">
                    <h3>PRIORITY ATTENTION REQUIRED</h3>
                    <p>There {'is' if len(overdue) == 1 else 'are'} {len(overdue)} case(s) that have passed their deadline.</p>
                </div>
                <div class="urgent-count">{len(overdue)}</div>
            </div>
        """
    
    html += f"""
            <div class="report-info">
                <div class="info-grid">
                    <div class="info-item">
                        <span class="info-label">DATE</span>
                        <span class="info-value">{fecha_referencia.strftime('%m/%d/%Y')}</span>
                    </div>
                    <div class="info-item">
                        <span class="info-label">ALERT PERIOD</span>
                        <span class="info-value">Next {DAYS_BEFORE} days</span>
                    </div>
                </div>
                <div class="recipient-badge">Responsible: {team_name}</div>
            </div>
            <div class="stats-title"><h3>Case Summary</h3></div>
            <div class="stats-container">
                <div class="stats-grid">
                    <div class="stat-card">
                        <div class="stat-number"><strong>{total_cases}</strong></div>
                        <div class="stat-label">Total Cases</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-number"><strong class="text-urgent">{urgent_count}</strong></div>
                        <div class="stat-label">Overdue Cases</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-number"><strong class="text-warning">{upcoming_count}</strong></div>
                        <div class="stat-label">Upcoming Deadline</div>
                    </div>
                </div>
            </div>
    """
    
    if len(overdue) > 0:
        html += f"""
            <div class="table-section">
                <div class="section-header">
                    <div class="section-title">OVERDUE CASES</div>
                    <div class="section-badge">{len(overdue)} cases</div>
                </div>
                <table class="data-table">
                    <thead><tr><th>Case ID</th><th>Case Type</th><th>Current Status</th><th>Deadline</th><th>Status</th><th>Office</th></tr></thead>
                    <tbody>
        """
        for _, row in overdue.iterrows():
            days_overdue = abs(row['Days_Until'])
            style_class, days_text = get_days_style(-days_overdue)
            html += f"""
                <tr>
                    <td><strong>{row.get('Case #', 'N/A')}</strong></td>
                    <td>{row.get('Case Type', 'N/A')}</td>
                    <td>{row.get('Case Status', 'N/A')}</td>
                    <td>{row.get('Deadline', 'N/A')}</td>
                    <td><span class="{style_class}">{days_text}</span></td>
                    <td>{row.get('Office Name', 'N/A')}</td>
                </tr>
            """
        html += "</tbody></table></div>"
    
    if len(upcoming) > 0:
        html += f"""
            <div class="table-section">
                <div class="section-header">
                    <div class="section-title">UPCOMING DEADLINE CASES</div>
                    <div class="section-badge">{len(upcoming)} cases</div>
                </div>
                <table class="data-table">
                    <thead><tr><th>Case ID</th><th>Case Type</th><th>Current Status</th><th>Deadline</th><th>Days Remaining</th><th>Office</th></tr></thead>
                    <tbody>
        """
        for _, row in upcoming.iterrows():
            days_left = row['Days_Until']
            style_class, days_text = get_days_style(days_left)
            html += f"""
                <tr>
                    <td><strong>{row.get('Case #', 'N/A')}</strong></td>
                    <td>{row.get('Case Type', 'N/A')}</td>
                    <td>{row.get('Case Status', 'N/A')}</td>
                    <td>{row.get('Deadline', 'N/A')}</td>
                    <td><span class="{style_class}">{days_text}</span></td>
                    <td>{row.get('Office Name', 'N/A')}</td>
                </tr>
            """
        html += "</tbody></table></div>"
    
    if rfe_excluded > 0:
        html += f"""
            <div class="rfe-note">
                ℹ️ <strong>Note:</strong> {rfe_excluded} case(s) with RFE status have been excluded from this report.
            </div>
        """
    
    html += f"""
            <div class="email-footer">
                <div class="footer-text">Legal Support Team Alerting System - Automatically generated</div>
                {logo_html}
                <div class="footer-note">© {fecha_referencia.year} Community Law Group · All rights reserved</div>
            </div>
        </div>
    </body>
    </html>
    """
    
    return html

# ============================================================
# FUNCIÓN PARA ENVIAR CORREO VÍA SMTP CON LOGO (CID)
# ============================================================

def enviar_correo_smtp(smtp_server, smtp_port, username, password, to_emails, cc_emails,
                       subject, html_body, logo_bytes=None):
    try:
        msg = MIMEMultipart('related')
        msg['Subject'] = subject
        msg['From'] = username
        msg['To'] = ", ".join(to_emails)
        if cc_emails:
            msg['CC'] = ", ".join(cc_emails)
        msg['X-Priority'] = '1'
        
        html_part = MIMEText(html_body, 'html')
        msg.attach(html_part)
        
        if logo_bytes:
            try:
                logo_cid = "company_logo_cid"
                image_part = MIMEImage(logo_bytes)
                image_part.add_header('Content-ID', f'<{logo_cid}>')
                image_part.add_header('Content-Disposition', 'inline', filename='logo.png')
                image_part.add_header('X-Attachment-Id', logo_cid)
                msg.attach(image_part)
                print("   🖼️ Logo adjuntado correctamente con CID")
            except Exception as e:
                print(f"   ⚠️ Error al adjuntar logo: {e}")
        else:
            print("   ⚠️ No se pudo obtener el logo para adjuntar")
        
        context = ssl.create_default_context()
        with smtplib.SMTP(smtp_server, smtp_port) as server:
            server.starttls(context=context)
            server.login(username, password)
            all_recipients = to_emails + (cc_emails if cc_emails else [])
            server.sendmail(username, all_recipients, msg.as_string())
        
        return True, "Correo enviado exitosamente"
    except Exception as e:
        return False, f"Error al enviar: {str(e)}"

# ============================================================
# FUNCIÓN PRINCIPAL DE PROCESAMIENTO
# ============================================================

def procesar_alertas(df, fecha_referencia, smtp_username, smtp_password, 
                     test_email=None, enviar_reales=False):
    resultados = []
    errores = []
    
    if 'TeamOwner' not in df.columns:
        return [], ["❌ Error: La columna 'TeamOwner' no existe en el archivo"]
    
    df['TeamOwner'] = df['TeamOwner'].astype(str).str.strip()
    df['TeamOwner'] = df['TeamOwner'].replace({'KIa': 'Kia', 'kia': 'Kia', 'KIA': 'Kia'})
    
    df_temp = df.copy()
    if 'Deadline' not in df_temp.columns:
        return [], ["❌ Error: La columna 'Deadline' no existe en el archivo"]
    
    df_temp['Days_Until'] = df_temp['Deadline'].apply(
        lambda x: calcular_dias_hasta_deadline(x, fecha_referencia)
    )
    
    mask_upcoming = (df_temp['Days_Until'] >= 0) & (df_temp['Days_Until'] <= DAYS_BEFORE)
    mask_overdue = (df_temp['Days_Until'] < 0) & (df_temp['Days_Until'] >= -DAYS_AFTER)
    df_alerts = df_temp[mask_upcoming | mask_overdue].copy()
    
    if len(df_alerts) == 0:
        return [], ["⚠️ No hay casos que requieran alerta en el período seleccionado"]
    
    alerts_by_team = {}
    for team in df_alerts['TeamOwner'].dropna().unique():
        team_cases = df_alerts[df_alerts['TeamOwner'] == team]
        if len(team_cases) > 0:
            alerts_by_team[team] = team_cases
    
    if not alerts_by_team:
        return [], ["⚠️ No se encontraron equipos con alertas"]
    
    logo_bytes = get_logo_bytes()
    logo_cid = "company_logo_cid" if logo_bytes else None
    
    if logo_bytes:
        print(f"✅ Logo obtenido: {len(logo_bytes)} bytes")
    else:
        print("⚠️ No se pudo obtener el logo para el correo")
    
    for team_name, team_cases in alerts_by_team.items():
        html_body = generar_html_correo(team_cases, team_name, fecha_referencia, logo_cid)
        if html_body is None:
            resultados.append(f"⏭️ {team_name}: Todos los casos son RFE - omitido")
            continue
        
        if test_email:
            to_email = [test_email]
            cc_email = []
            subject = f"[TEST] ST LEGAL - Case Report - {team_name} - {fecha_referencia.strftime('%m/%d/%Y')}"
        else:
            to_email = [get_team_email(team_name)] if get_team_email(team_name) else []
            cc_email = get_cc_for_team(team_name)
            subject = f"ST LEGAL - Case Deadline Report - {team_name} - {fecha_referencia.strftime('%m/%d/%Y')}"
        
        if not to_email:
            resultados.append(f"❌ {team_name}: No hay email configurado")
            continue
        
        if enviar_reales and smtp_username and smtp_password:
            success, msg = enviar_correo_smtp(
                SMTP_SERVER, SMTP_PORT,
                smtp_username, smtp_password,
                to_email, cc_email,
                subject, html_body,
                logo_bytes
            )
            if success:
                resultados.append(f"✅ {team_name}: Enviado a {', '.join(to_email)}")
            else:
                errores.append(f"❌ {team_name}: {msg}")
        else:
            resultados.append(f"📄 {team_name}: Correo listo (modo simulación)")
            with open(f"preview_{team_name}.html", 'w', encoding='utf-8') as f:
                f.write(html_body)
            resultados.append(f"   📄 Preview guardado: preview_{team_name}.html")
    
    return resultados, errores

# ============================================================
# PALETA DE COLORES
# ============================================================

def get_colors(dark_mode=False):
    if dark_mode:
        return {
            "bg": "#0a0e14",
            "card_bg": "#161a22",
            "card_border": "#2a303a",
            "text_primary": "#e8edf2",
            "text_secondary": "#8a9bb0",
            "text_dark": "#f0f4f8",
            "text_sidebar": "#ffffff",
            "sidebar_bg": "#0d1117",
            "blue": "#4a8bc2",
            "blue_dark": "#2a5a7a",
            "red": "#e74c3c",
            "red_dark": "#a93226",
            "yellow": "#f1c40f",
            "yellow_dark": "#b7950b",
            "green": "#2ecc71",
            "green_dark": "#1a7a42",
            "purple": "#8e44ad",
            "orange": "#e67e22",
            "teal": "#1abc9c",
            "urgent": "#e74c3c",
            "warning": "#f39c12",
            "success": "#2ecc71",
            "info": "#3498db",
            "header_bg": "#0d1117",
            "banner_grad1": "#1a2744",
            "banner_grad2": "#2a4a6a",
            "metric_bg": "#1c2430",
            "shadow": "rgba(0,0,0,0.6)",
            "sidebar_grad1": "#0d1117",
            "sidebar_grad2": "#161a22"
        }
    else:
        return {
            "bg": "#e8edf2",
            "card_bg": "#ffffff",
            "card_border": "#c8d0d8",
            "text_primary": "#1a2a3a",
            "text_secondary": "#4a5a6a",
            "text_dark": "#0d1a2a",
            "text_sidebar": "#1a2a3a",
            "sidebar_bg": "#f0f4f8",
            "blue": "#1a4a7a",
            "blue_dark": "#0d2a4a",
            "red": "#c0392b",
            "red_dark": "#922b21",
            "yellow": "#d4ac0d",
            "yellow_dark": "#9a7d0a",
            "green": "#1e8449",
            "green_dark": "#145a32",
            "purple": "#6c3483",
            "orange": "#ca6f1e",
            "teal": "#148f77",
            "urgent": "#c0392b",
            "warning": "#e67e22",
            "success": "#27ae60",
            "info": "#1e40af",
            "header_bg": "#f0f4f8",
            "banner_grad1": "#1a3a5c",
            "banner_grad2": "#4a7c9c",
            "metric_bg": "#eef2f6",
            "shadow": "rgba(0,0,0,0.1)",
            "sidebar_grad1": "#e8edf2",
            "sidebar_grad2": "#d5dde6"
        }

# ============================================================
# INTERFAZ STREAMLIT
# ============================================================

st.set_page_config(
    page_title="ST LEGAL Alert System",
    page_icon="⚖️",
    layout="wide",
    initial_sidebar_state="expanded"
)

if 'dark_mode' not in st.session_state:
    st.session_state.dark_mode = False

# ============================================================
# CSS DE LA INTERFAZ
# ============================================================

def inject_css(colors):
    st.markdown(f"""
    <style>
        #MainMenu {{ visibility: hidden; }}
        footer {{ visibility: hidden; }}
        
        .stApp {{
            background-color: {colors['bg']};
        }}
        
        @keyframes fadeInUp {{
            from {{ opacity: 0; transform: translateY(20px); }}
            to {{ opacity: 1; transform: translateY(0); }}
        }}
        
        @keyframes pulse {{
            0% {{ transform: scale(1); }}
            50% {{ transform: scale(1.03); }}
            100% {{ transform: scale(1); }}
        }}
        
        @keyframes slideIn {{
            from {{ opacity: 0; transform: translateX(-20px); }}
            to {{ opacity: 1; transform: translateX(0); }}
        }}
        
        .animate {{ animation: fadeInUp 0.6s ease-out; }}
        .animate-delay-1 {{ animation-delay: 0.1s; }}
        .animate-delay-2 {{ animation-delay: 0.2s; }}
        .animate-delay-3 {{ animation-delay: 0.3s; }}
        .animate-delay-4 {{ animation-delay: 0.4s; }}
        
        .css-1d391kg {{
            background: linear-gradient(180deg, {colors['sidebar_grad1']}, {colors['sidebar_grad2']}) !important;
            border-right: 2px solid {colors['blue']} !important;
            animation: fadeInUp 0.5s ease-out;
        }}
        
        .css-1d391kg .stMarkdown,
        .css-1d391kg .stText,
        .css-1d391kg .stCaption,
        .css-1d391kg label,
        .css-1d391kg .stMarkdown p {{
            color: {colors['text_sidebar']} !important;
        }}
        
        .sidebar-title {{
            text-align: center;
            padding: 16px 0 12px 0;
            border-bottom: 2px solid {colors['blue']};
            margin-bottom: 16px;
            animation: pulse 3s infinite;
        }}
        
        .sidebar-title .main {{
            font-weight: 800;
            color: {colors['text_sidebar']};
            font-size: 24px;
            letter-spacing: -0.3px;
        }}
        
        .sidebar-title .sub {{
            font-size: 12px;
            color: {colors['text_secondary']};
            letter-spacing: 1.5px;
            font-weight: 600;
        }}
        
        .sidebar-section {{
            background: rgba(255,255,255,0.06);
            border-radius: 10px;
            padding: 12px 16px;
            margin-bottom: 12px;
            border: 1px solid rgba(255,255,255,0.08);
            transition: all 0.3s ease;
            animation: fadeInUp 0.6s ease-out;
        }}
        
        .sidebar-section:hover {{
            background: rgba(255,255,255,0.10);
            border-color: {colors['blue']};
            transform: translateX(4px);
        }}
        
        .sidebar-section .icon {{
            font-size: 18px;
            margin-right: 8px;
        }}
        
        .sidebar-section .label {{
            font-weight: 700;
            color: {colors['text_sidebar']};
            font-size: 14px;
        }}
        
        .sidebar-section .desc {{
            font-size: 12px;
            color: {colors['text_secondary']};
            margin-top: 2px;
        }}
        
        .css-1d391kg .stTextInput > div > div > input {{
            background-color: {colors['card_bg']} !important;
            color: {colors['text_sidebar']} !important;
            border-color: {colors['card_border']} !important;
            border-radius: 8px !important;
            padding: 10px 14px !important;
            font-size: 14px !important;
            font-weight: 500 !important;
            transition: all 0.3s ease !important;
        }}
        
        .css-1d391kg .stTextInput > div > div > input:focus {{
            border-color: {colors['blue']} !important;
            box-shadow: 0 0 20px rgba(74, 139, 194, 0.2) !important;
        }}
        
        .css-1d391kg .stTextInput > div > div > input::placeholder {{
            color: {colors['text_secondary']} !important;
            opacity: 0.7 !important;
        }}
        
        .css-1d391kg .stDateInput > div > div > input {{
            background-color: {colors['card_bg']} !important;
            color: {colors['text_sidebar']} !important;
            border-color: {colors['card_border']} !important;
            border-radius: 8px !important;
            padding: 10px 14px !important;
            font-size: 14px !important;
            font-weight: 500 !important;
        }}
        
        .css-1d391kg .stFileUploader > div > button {{
            background-color: {colors['card_bg']} !important;
            color: {colors['text_sidebar']} !important;
            border-color: {colors['card_border']} !important;
            border-radius: 8px !important;
            font-weight: 600 !important;
            transition: all 0.3s ease !important;
        }}
        
        .css-1d391kg .stFileUploader > div > button:hover {{
            background-color: {colors['blue']} !important;
            color: white !important;
            border-color: {colors['blue']} !important;
        }}
        
        .css-1d391kg .stCheckbox label {{
            color: {colors['text_sidebar']} !important;
            font-weight: 600 !important;
            font-size: 14px !important;
        }}
        
        .css-1d391kg .stButton > button {{
            border-radius: 10px !important;
            font-weight: 700 !important;
            font-size: 15px !important;
            padding: 10px 16px !important;
            transition: all 0.3s ease !important;
            border: none !important;
        }}
        
        .css-1d391kg .stButton > button:first-child {{
            background: linear-gradient(135deg, {colors['blue']}, {colors['purple']}) !important;
            color: white !important;
        }}
        
        .css-1d391kg .stButton > button:first-child:hover {{
            transform: translateY(-3px) !important;
            box-shadow: 0 6px 25px rgba(74, 139, 194, 0.4) !important;
        }}
        
        .css-1d391kg .stButton > button:last-child {{
            background: rgba(255,255,255,0.10) !important;
            color: {colors['text_sidebar']} !important;
            border: 1px solid rgba(255,255,255,0.15) !important;
        }}
        
        .css-1d391kg .stButton > button:last-child:hover {{
            background: rgba(255,255,255,0.20) !important;
            transform: translateY(-3px) !important;
        }}
        
        .css-1d391kg .stCaption {{
            color: {colors['text_secondary']} !important;
            font-size: 11px !important;
            font-weight: 500 !important;
        }}
        
        .css-1d391kg hr {{
            border-color: {colors['card_border']} !important;
            margin: 12px 0 !important;
            opacity: 0.3 !important;
        }}
        
        .metric-container {{
            border-radius: 12px;
            padding: 18px 16px;
            text-align: center;
            border: 2px solid {colors['card_border']};
            background-color: {colors['metric_bg']};
            transition: all 0.3s ease;
            animation: fadeInUp 0.5s ease-out;
            min-height: 100px;
            display: flex;
            flex-direction: column;
            justify-content: center;
        }}
        
        .metric-container:hover {{
            transform: translateY(-4px);
            box-shadow: 0 6px 20px {colors['shadow']};
        }}
        
        .metric-value {{
            font-size: 38px;
            font-weight: 800;
            line-height: 1.2;
        }}
        
        .metric-label {{
            font-size: 14px;
            font-weight: 700;
            text-transform: uppercase;
            letter-spacing: 0.8px;
            margin-top: 4px;
        }}
        
        .metric-red .metric-value {{ color: {colors['red']}; }}
        .metric-red .metric-label {{ color: {colors['red_dark']}; }}
        .metric-red {{ border-color: {colors['red']}; }}
        
        .metric-yellow .metric-value {{ color: {colors['yellow_dark']}; }}
        .metric-yellow .metric-label {{ color: {colors['yellow_dark']}; }}
        .metric-yellow {{ border-color: {colors['yellow']}; }}
        
        .metric-green .metric-value {{ color: {colors['green']}; }}
        .metric-green .metric-label {{ color: {colors['green_dark']}; }}
        .metric-green {{ border-color: {colors['green']}; }}
        
        .metric-blue .metric-value {{ color: {colors['blue']}; }}
        .metric-blue .metric-label {{ color: {colors['blue_dark']}; }}
        .metric-blue {{ border-color: {colors['blue']}; }}
        
        .metric-purple .metric-value {{ color: {colors['purple']}; }}
        .metric-purple .metric-label {{ color: {colors['purple']}; }}
        .metric-purple {{ border-color: {colors['purple']}; }}
        
        .result-success {{
            background-color: rgba(46, 204, 113, 0.10);
            border-left: 6px solid {colors['green']};
            padding: 14px 18px;
            border-radius: 6px;
            margin: 6px 0;
            color: {colors['text_primary']};
            font-size: 15px;
            font-weight: 500;
            animation: slideIn 0.4s ease-out;
        }}
        
        .result-error {{
            background-color: rgba(231, 76, 60, 0.10);
            border-left: 6px solid {colors['red']};
            padding: 14px 18px;
            border-radius: 6px;
            margin: 6px 0;
            color: {colors['text_primary']};
            font-size: 15px;
            font-weight: 500;
            animation: slideIn 0.4s ease-out;
        }}
        
        .result-info {{
            background-color: rgba(52, 152, 219, 0.10);
            border-left: 6px solid {colors['info']};
            padding: 14px 18px;
            border-radius: 6px;
            margin: 6px 0;
            color: {colors['text_primary']};
            font-size: 15px;
            font-weight: 500;
            animation: slideIn 0.4s ease-out;
        }}
        
        .footer {{
            text-align: center;
            padding: 20px;
            color: {colors['text_secondary']};
            font-size: 13px;
            border-top: 2px solid {colors['card_border']};
            margin-top: 30px;
            animation: fadeInUp 0.6s ease-out;
        }}
        
        h1, h2, h3, h4, h5, h6 {{
            color: {colors['text_primary']} !important;
            font-weight: 700 !important;
        }}
        
        .stMarkdown, .stText, .stCaption, label {{
            color: {colors['text_secondary']} !important;
        }}
        
        .banner-container {{
            border-radius: 14px;
            overflow: hidden;
            margin-bottom: 25px;
            animation: fadeInUp 0.5s ease-out;
            box-shadow: 0 4px 20px {colors['shadow']};
        }}
        
        .streamlit-expanderHeader {{
            color: {colors['text_primary']} !important;
            font-weight: 700 !important;
            font-size: 15px !important;
            background-color: {colors['metric_bg']} !important;
            border-radius: 8px !important;
        }}
        
        .stDataFrame {{
            border-radius: 10px !important;
            overflow: hidden !important;
        }}
        
        .stSpinner > div {{
            border-color: {colors['blue']} !important;
        }}
        
        .text-large {{
            font-size: 18px;
            line-height: 1.6;
        }}
        
        .text-dark {{ color: {colors['text_dark']} !important; font-weight: 700; }}
    </style>
    """, unsafe_allow_html=True)

# ============================================================
# BANNER CON IMAGEN O RESPALDO
# ============================================================

def render_banner(colors):
    banner_base64 = get_banner_base64()
    
    if banner_base64:
        st.markdown(f"""
        <div class="banner-container">
            <img src="{banner_base64}" alt="ST LEGAL Alert System" style="width: 100%; height: auto; display: block;">
        </div>
        """, unsafe_allow_html=True)
    else:
        st.markdown(f"""
        <div style="
            background: linear-gradient(135deg, {colors['banner_grad1']}, {colors['banner_grad2']});
            padding: 40px 50px;
            border-radius: 14px;
            margin-bottom: 25px;
            box-shadow: 0 6px 25px {colors['shadow']};
            animation: fadeInUp 0.5s ease-out;
        ">
            <div style="display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 15px;">
                <div>
                    <h1 style="color: white; font-size: 34px; font-weight: 800; margin: 0; letter-spacing: -0.5px; text-shadow: 0 2px 4px rgba(0,0,0,0.2);">
                        ⚖️ ST LEGAL
                    </h1>
                    <p style="color: rgba(255,255,255,0.95); font-size: 17px; margin: 6px 0 0 0; font-weight: 500;">
                        Deadline and Case Management System
                    </p>
                </div>
                <div style="display: flex; gap: 12px; align-items: center; flex-wrap: wrap;">
                    <span style="
                        background: rgba(255,255,255,0.2);
                        color: white;
                        padding: 8px 22px;
                        border-radius: 30px;
                        font-size: 14px;
                        font-weight: 700;
                        backdrop-filter: blur(4px);
                    ">v2.0</span>
                    <span style="
                        background: rgba(46, 204, 113, 0.3);
                        color: #2ecc71;
                        padding: 8px 22px;
                        border-radius: 30px;
                        font-size: 14px;
                        font-weight: 700;
                        border: 1px solid rgba(46, 204, 113, 0.3);
                        backdrop-filter: blur(4px);
                        animation: pulse 2s infinite;
                    ">● Active</span>
                </div>
            </div>
        </div>
        """, unsafe_allow_html=True)

# ============================================================
# CONFIGURACIÓN Y RENDERIZADO PRINCIPAL
# ============================================================

colors = get_colors(st.session_state.dark_mode)
inject_css(colors)
render_banner(colors)

# ============================================================
# BARRA LATERAL
# ============================================================

with st.sidebar:
    st.markdown(f"""
    <div class="sidebar-title">
        <div class="main">⚖️ ST LEGAL</div>
        <div class="sub">ALERT SYSTEM</div>
    </div>
    """, unsafe_allow_html=True)
    
    st.markdown("""
    <div class="sidebar-section">
        <div style="display: flex; align-items: center; gap: 8px;">
            <span class="icon">🌙</span>
            <span class="label">Modo oscuro</span>
        </div>
    </div>
    """, unsafe_allow_html=True)
    
    dark_mode_toggle = st.toggle("", value=st.session_state.dark_mode, label_visibility="collapsed")
    if dark_mode_toggle != st.session_state.dark_mode:
        st.session_state.dark_mode = dark_mode_toggle
        st.rerun()
    
    st.markdown("""
    <div class="sidebar-section">
        <div style="display: flex; align-items: center; gap: 8px;">
            <span class="icon">📧</span>
            <span class="label">Correo</span>
        </div>
        <div class="desc">Configuración SMTP de Outlook</div>
    </div>
    """, unsafe_allow_html=True)
    
    smtp_username = st.text_input("Usuario", value="", placeholder="tu@email.com", label_visibility="collapsed")
    smtp_password = st.text_input("Contraseña", type="password", placeholder="••••••••", label_visibility="collapsed")
    
    st.markdown("""
    <div class="sidebar-section">
        <div style="display: flex; align-items: center; gap: 8px;">
            <span class="icon">📁</span>
            <span class="label">Datos</span>
        </div>
        <div class="desc">Carga tu archivo Excel</div>
    </div>
    """, unsafe_allow_html=True)
    
    uploaded_file = st.file_uploader("Archivo Excel", type=['xlsx', 'xls'], label_visibility="collapsed")
    
    st.markdown("""
    <div class="sidebar-section">
        <div style="display: flex; align-items: center; gap: 8px;">
            <span class="icon">⚙️</span>
            <span class="label">Fecha</span>
        </div>
        <div class="desc">Fecha de referencia</div>
    </div>
    """, unsafe_allow_html=True)
    
    fecha_referencia = st.date_input("Referencia", value=datetime.now().date(), label_visibility="collapsed")
    
    st.markdown("""
    <div class="sidebar-section">
        <div style="display: flex; align-items: center; gap: 8px;">
            <span class="icon">🔬</span>
            <span class="label">Modo prueba</span>
        </div>
        <div class="desc">Envía a un solo correo de prueba</div>
    </div>
    """, unsafe_allow_html=True)
    
    test_mode = st.checkbox("", label_visibility="collapsed")
    test_email = st.text_input("Correo de prueba", placeholder="test@email.com", label_visibility="collapsed") if test_mode else None
    
    st.markdown("---")
    
    col_btn1, col_btn2 = st.columns(2)
    with col_btn1:
        enviar_reales = st.button("📨 Enviar", type="primary", use_container_width=True)
    with col_btn2:
        simular = st.button("📄 Simular", use_container_width=True)
    
    st.markdown("---")
    st.caption("🔒 TLS seguro · Sin almacenamiento")

# ============================================================
# ÁREA PRINCIPAL
# ============================================================

if uploaded_file is not None:
    df = pd.read_excel(uploaded_file)
    
    st.markdown(f"<div class='text-large text-dark' style='font-weight: 700; font-size: 20px; margin-bottom: 16px;'>📊 Resumen de datos</div>", unsafe_allow_html=True)
    
    col_m1, col_m2, col_m3, col_m4 = st.columns(4)
    
    with col_m1:
        st.markdown(f"""
        <div class="metric-container metric-blue animate animate-delay-1">
            <div class="metric-value">{len(df)}</div>
            <div class="metric-label">Registros</div>
        </div>
        """, unsafe_allow_html=True)
    
    if 'TeamOwner' in df.columns:
        teams = df['TeamOwner'].dropna().unique()
        with col_m2:
            st.markdown(f"""
            <div class="metric-container metric-purple animate animate-delay-2">
                <div class="metric-value">{len(teams)}</div>
                <div class="metric-label">Equipos</div>
            </div>
            """, unsafe_allow_html=True)
    
    if 'Case Status' in df.columns:
        rfe_count = df['Case Status'].astype(str).str.upper().str.contains('RFE', na=False).sum()
        with col_m3:
            st.markdown(f"""
            <div class="metric-container metric-yellow animate animate-delay-3">
                <div class="metric-value">{rfe_count}</div>
                <div class="metric-label">RFE</div>
            </div>
            """, unsafe_allow_html=True)
    
    if 'Desktime' in df.columns:
        on_time = len(df[df['Desktime'] == 'On time'])
        with col_m4:
            st.markdown(f"""
            <div class="metric-container metric-green animate animate-delay-4">
                <div class="metric-value">{on_time}</div>
                <div class="metric-label">On Time</div>
            </div>
            """, unsafe_allow_html=True)
    
    with st.expander("👁️ Vista previa de datos"):
        st.dataframe(df.head(10), use_container_width=True)
    
    if enviar_reales or simular:
        if enviar_reales and (not smtp_username or not smtp_password):
            st.error("⚠️ Ingresa tus credenciales de Outlook para enviar correos reales")
        else:
            with st.spinner("⏳ Procesando alertas..."):
                resultados, errores = procesar_alertas(
                    df, fecha_referencia, smtp_username, smtp_password,
                    test_email, enviar_reales
                )
            
            st.markdown("---")
            st.markdown(f"<div style='font-weight: 700; color: {colors['text_primary']}; font-size: 20px;'>📋 Resultados</div>", unsafe_allow_html=True)
            
            if errores:
                for err in errores:
                    st.markdown(f'<div class="result-error">{err}</div>', unsafe_allow_html=True)
            
            if resultados:
                for res in resultados:
                    if res.startswith("✅"):
                        st.markdown(f'<div class="result-success">{res}</div>', unsafe_allow_html=True)
                    elif res.startswith("❌"):
                        st.markdown(f'<div class="result-error">{res}</div>', unsafe_allow_html=True)
                    else:
                        st.markdown(f'<div class="result-info">{res}</div>', unsafe_allow_html=True)
            
            if enviar_reales and not errores:
                st.balloons()
                st.success("🎉 Proceso completado exitosamente")

else:
    st.markdown(f"""
    <div style="
        text-align: center;
        padding: 100px 30px;
        background-color: {colors['card_bg']};
        border-radius: 14px;
        border: 2px dashed {colors['card_border']};
        animation: fadeInUp 0.6s ease-out;
    ">
        <div style="font-size: 72px; margin-bottom: 24px;">📂</div>
        <h2 style="color: {colors['text_primary']}; font-weight: 800; margin: 0; font-size: 28px;">Carga tu archivo Excel</h2>
        <p style="color: {colors['text_secondary']}; margin: 12px 0 0 0; font-size: 17px;">
            Sube un archivo con los casos para generar alertas de vencimiento
        </p>
        <div style="margin-top: 20px; display: flex; gap: 12px; justify-content: center; flex-wrap: wrap;">
            <span style="background: {colors['metric_bg']}; padding: 6px 20px; border-radius: 30px; font-size: 14px; font-weight: 600; color: {colors['text_secondary']};">TeamOwner</span>
            <span style="background: {colors['metric_bg']}; padding: 6px 20px; border-radius: 30px; font-size: 14px; font-weight: 600; color: {colors['text_secondary']};">Deadline</span>
            <span style="background: {colors['metric_bg']}; padding: 6px 20px; border-radius: 30px; font-size: 14px; font-weight: 600; color: {colors['text_secondary']};">Case Status</span>
        </div>
    </div>
    """, unsafe_allow_html=True)

# ============================================================
# FOOTER
# ============================================================

st.markdown(f"""
<div class="footer">
    <strong style="color: {colors['text_primary']};">ST LEGAL Alert System</strong> · Data &amp; Efficiency Team
    <br>
    © {datetime.now().year} Community Law Group
</div>
""", unsafe_allow_html=True)
