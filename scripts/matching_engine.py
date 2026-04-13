#!/usr/bin/env python3
"""
Eşleştirme Motoru
Şirket ihtiyaçlarına göre otomatik aday önerileri yapar
"""

import requests
import json
import os
import re
from datetime import datetime

# GitHub API ayarları
github_repo = os.getenv("GITHUB_REPOSITORY", "VB10/staj2026")
github_api_url = f"https://api.github.com/repos/{github_repo}"

# Import token from config file
try:
    from config import GITHUB_TOKEN
    github_headers = {
        "Accept": "application/vnd.github.v3+json",
        "Authorization": f"token {GITHUB_TOKEN}"
    }
except ImportError:
    github_token = os.getenv("GITHUB_TOKEN")
    if github_token:
        github_headers = {
            "Accept": "application/vnd.github.v3+json",
            "Authorization": f"token {github_token}"
        }
    else:
        print("GITHUB_TOKEN bulunamadı!")
        exit(1)

def parse_issue_title(title):
    """Issue başlığını parse eder"""
    pattern = re.compile(r"^(.*?)\s*\[(.*?)\]\[(.*?)\]\[(.*?)\]\[(.*?)\]$")
    cleaned_title = (
        title.replace(" [", "[")
        .replace("[ ", "[")
        .replace(" ]", "]")
        .replace("] ", "]")
        .strip()
    )
    
    match = pattern.match(cleaned_title)
    if not match:
        return None
    
    name, category, location, intern_type, duration = match.groups()
    return {
        "name": name.strip(),
        "category": [c.strip() for c in category.split(",")],
        "location": [l.strip() for l in location.split(",")],
        "intern_type": intern_type.strip(),
        "duration": [d.strip() for d in duration.split(",")]
    }

def parse_company_issue(issue_body):
    """Şirket issue'sunu parse eder"""
    company_info = {
        "name": "",
        "positions": [],
        "location": [],
        "staj_tipi": []
    }
    
    # Şirket adını başlıktan al
    title_match = re.match(r"\[(.+?)\]\s*-\s*Staj Fırsatı", issue_body.split('\n')[0] if issue_body else "")
    if title_match:
        company_info["name"] = title_match.group(1)
    
    # Pozisyonları çıkar
    position_map = {
        'Mobile': 'mobile',
        'Backend': 'backend',
        'Frontend': 'frontend',
        'PM': 'pm',
        'QA': 'qa',
        'Game Development': 'game',
        'Data Science': 'data-science',
        'Data Analyst': 'data-analyst',
        'Database': 'database',
        'Embedded': 'embedded',
        'Cyber Security': 'cyber-security',
        'Blockchain': 'blockchain',
        'System': 'system',
        'Networking': 'networking',
        'Hardware': 'hardware',
        'SAP ABAP': 'sap-abap',
        'Machine Learning': 'ai-ml',
    }
    
    for key, value in position_map.items():
        if f'- [x] {key}' in issue_body.lower() or f'- [X] {key}' in issue_body:
            company_info["positions"].append(value)
    
    # Staj tipini çıkar
    if '- [x] Uzaktan' in issue_body or '- [X] Uzaktan' in issue_body:
        company_info["location"].append("uzaktan")
    if '- [x] Yüzyüze' in issue_body or '- [X] Yüzyüze' in issue_body:
        company_info["location"].append("yüzyüze")
    if '- [x] Hibrit' in issue_body or '- [X] Hibrit' in issue_body:
        company_info["location"].extend(["uzaktan", "yüzyüze"])
    
    return company_info

def calculate_match_score(candidate, company):
    """Eşleşme skorunu hesaplar"""
    score = 0
    
    # Kategori eşleşmesi (en önemli)
    candidate_categories = set(candidate["category"])
    company_positions = set(company["positions"])
    
    if candidate_categories & company_positions:
        score += 50
        # Kaç kategori eşleşiyor
        matches = len(candidate_categories & company_positions)
        score += matches * 10
    
    # Lokasyon eşleşmesi
    candidate_locations = set(candidate["location"])
    company_locations = set(company["location"])
    
    if candidate_locations & company_locations:
        score += 20
    
    # Staj tipi (zorunlu öncelikli)
    if candidate["intern_type"] == "zorunlu":
        score += 10
    
    return score

def find_matching_candidates(company_info):
    """Şirket için uygun adayları bulur"""
    # Tüm açık issue'ları çek
    all_issues = []
    page = 1
    
    while True:
        try:
            response = requests.get(
                f"{github_api_url}/issues",
                headers=github_headers,
                params={
                    "state": "open",
                    "per_page": 100,
                    "page": page
                }
            )
            
            if response.status_code != 200:
                break
            
            issues = response.json()
            if not issues:
                break
            
            all_issues.extend(issues)
            page += 1
            
            if len(issues) < 100:
                break
        except Exception as e:
            print(f"Error: {str(e)}")
            break
    
    # Adayları parse et ve skorla
    candidates = []
    for issue in all_issues:
        # Şirket issue'larını atla
        if 'company-opportunity' in [label['name'] for label in issue.get('labels', [])]:
            continue
        
        parsed = parse_issue_title(issue["title"])
        if not parsed:
            continue
        
        score = calculate_match_score(parsed, company_info)
        
        if score > 0:
            candidates.append({
                "issue": issue,
                "parsed": parsed,
                "score": score
            })
    
    # Skora göre sırala
    candidates.sort(key=lambda x: x["score"], reverse=True)
    
    return candidates[:20]  # En iyi 20 aday

def notify_company(company_issue_number, matches):
    """Şirkete eşleşmeleri bildirir"""
    if not matches:
        return
    
    comment = "## 🎯 Size Uygun Adaylar\n\n"
    comment += f"Toplam **{len(matches)}** aday bulundu. En uygun adaylar:\n\n"
    
    for i, match in enumerate(matches[:10], 1):
        candidate = match["parsed"]
        issue = match["issue"]
        score = match["score"]
        
        categories_str = ", ".join(candidate["category"])
        locations_str = ", ".join(candidate["location"])
        
        comment += f"### {i}. [{candidate['name']}]({issue['html_url']}) - Skor: {score}\n"
        comment += f"- **Alanlar**: {categories_str}\n"
        comment += f"- **Lokasyon**: {locations_str}\n"
        comment += f"- **Staj Tipi**: {candidate['intern_type']}\n"
        comment += f"- **Süre**: {', '.join(candidate['duration'])}\n\n"
    
    if len(matches) > 10:
        comment += f"\n*...ve {len(matches) - 10} aday daha*\n"
    
    comment += "\n---\n"
    comment += "*Bu eşleştirme otomatik olarak oluşturulmuştur.*\n"
    
    try:
        response = requests.post(
            f"{github_api_url}/issues/{company_issue_number}/comments",
            headers=github_headers,
            json={"body": comment}
        )
        
        if response.status_code == 201:
            print(f"Şirkete bildirim gönderildi: Issue #{company_issue_number}")
            return True
    except Exception as e:
        print(f"Bildirim gönderilemedi: {str(e)}")
    
    return False

def notify_candidates(company_info, matches):
    """Adaylara şirket hakkında bildirim gönderir"""
    company_name = company_info.get("name", "Bir şirket")
    
    for match in matches[:5]:  # En iyi 5 adaya bildirim
        issue = match["issue"]
        candidate = match["parsed"]
        
        comment = f"## 🎉 Yeni Fırsat!\n\n"
        comment += f"Merhaba @{issue['user']['login']}, **{company_name}** şirketi sizin profil uygun staj fırsatları sunuyor!\n\n"
        comment += f"Detaylar için [şirket başvurusunu](https://github.com/{github_repo}/issues/{company_info.get('issue_number', '')}) inceleyebilirsiniz.\n\n"
        comment += "İyi şanslar! 🚀\n"
        
        try:
            response = requests.post(
                f"{github_api_url}/issues/{issue['number']}/comments",
                headers=github_headers,
                json={"body": comment}
            )
            
            if response.status_code == 201:
                print(f"Adaya bildirim gönderildi: Issue #{issue['number']}")
        except Exception as e:
            print(f"Bildirim gönderilemedi: {str(e)}")

def main():
    # Yeni eklenen şirket issue'larını bul
    try:
        response = requests.get(
            f"{github_api_url}/issues",
            headers=github_headers,
            params={
                "state": "open",
                "labels": "approved-company",
                "per_page": 10
            }
        )
        
        if response.status_code != 200:
            print(f"Error fetching company issues: {response.status_code}")
            return
        
        company_issues = response.json()
        
        for company_issue in company_issues:
            company_info = parse_company_issue(company_issue["body"])
            company_info["issue_number"] = company_issue["number"]
            
            if not company_info["positions"]:
                continue
            
            print(f"Eşleştirme yapılıyor: {company_info['name']}")
            
            matches = find_matching_candidates(company_info)
            
            if matches:
                print(f"{len(matches)} aday bulundu")
                notify_company(company_issue["number"], matches)
                notify_candidates(company_info, matches)
            else:
                print("Eşleşen aday bulunamadı")
    
    except Exception as e:
        print(f"Error: {str(e)}")

if __name__ == "__main__":
    main()
