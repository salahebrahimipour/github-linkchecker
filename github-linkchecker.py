import csv
from github import Github, GithubException
import requests
import re
import os
from datetime import datetime
import time
import warnings


"""
This python code is developed to easily monitor links available in your github account and create a report by 
providing you with a csv file of broken links inside your account and repositories.
use the code, fork it, improve it, and get your github account's broken links fixed!

Copyright (c) 2025 [Salah Ebrahimipour]
"""

# Suppress urllib3 SSL warning
warnings.filterwarnings("ignore", category=UserWarning, module="urllib3")

def extract_links(text):
    # Find [text](url) links
    inline_links = re.findall(r'\[([^\]]+)\]\(([^)]+)\)', text)
    inline_urls = [link[1] for link in inline_links]
    # Find plain URLs
    plain_urls = re.findall(r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*(),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+', text)
    # Combine and remove duplicates
    return list(set(inline_urls + plain_urls))

def get_full_url(link, repo):
    if link.startswith('http://') or link.startswith('https://'):
        return link
    # Handle relative paths
    path = link.lstrip('/')
    return f"https://github.com/{repo.full_name}/blob/{repo.default_branch}/{path}"

def check_link(url, retries=2):
    for attempt in range(retries):
        try:
            # Use HEAD request first, fallback to GET if needed
            response = requests.head(url, allow_redirects=True, timeout=10)
            if response.status_code in (405, 403):  # HEAD not allowed
                response = requests.get(url, allow_redirects=True, timeout=10)
            return response.status_code, response.status_code == 200
        except requests.RequestException:
            if attempt == retries - 1:
                return None, False
            continue
    return None, False

def crawl_files(repo, path='', broken_links=None):
    if broken_links is None:
        broken_links = []
    
    try:
        contents = repo.get_contents(path)
        for content in contents:
            if content.type == 'dir':
                # Recursively crawl directories
                crawl_files(repo, content.path, broken_links)
            elif content.path.endswith(('.md', '.rst', '.txt')):  # Process markdown, reStructuredText, and text files
                try:
                    file_content = content.decoded_content.decode('utf-8')
                    links = extract_links(file_content)
                    for link in links:
                        full_url = get_full_url(link, repo)
                        status, is_valid = check_link(full_url)
                        if not is_valid:
                            broken_links.append({
                                'repo': repo.full_name,
                                'file': content.path,
                                'link': link,
                                'full_url': full_url,
                                'status_code': status if status else 'Error'
                            })
                except Exception as e:
                    print(f"Error processing file {content.path} in repo {repo.name}: {e}")
    except GithubException as e:
        if e.status == 403 and 'rate limit exceeded' in str(e).lower():
            reset_time = int(e.data.get('reset', time.time() + 3600))
            wait_time = max(0, reset_time - int(time.time())) + 5
            print(f"Rate limit exceeded. Waiting {wait_time} seconds until reset...")
            time.sleep(wait_time)
            # Retry the same path after waiting
            return crawl_files(repo, path, broken_links)
        else:
            print(f"Error accessing path {path} in repo {repo.name}: {e}")
    
    return broken_links

def write_to_csv(broken_links, output_file):
    if not broken_links:
        print("No broken links found.")
        return
    
    with open(output_file, 'w', newline='', encoding='utf-8') as csvfile:
        fieldnames = ['Repository', 'File', 'Link', 'Full URL', 'Status Code']
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        for link in broken_links:
            writer.writerow({
                'Repository': link['repo'],
                'File': link['file'],
                'Link': link['link'],
                'Full URL': link['full_url'],
                'Status Code': link['status_code']
            })
    print(f"Broken links written to {output_file}")

def main():
    # Configuration
    token = os.getenv('GITHUB_TOKEN', '#########################################')    # Replace with your GitHub Token
    username = "###########"  # Replace with target GitHub username
    output_file = f"broken_links_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"

    # Check if token is provided
    if not token:
        print("Warning: No GitHub token provided. Rate limits are stricter for unauthenticated requests (60 requests/hour).")
        print("Set the GITHUB_TOKEN environment variable with a Personal Access Token for higher limits.")

    # Initialize GitHub client
    g = Github(token) if token else Github()
    
    try:
        user = g.get_user(username)
    except GithubException as e:
        if e.status == 403 and 'rate limit exceeded' in str(e).lower():
            reset_time = int(e.data.get('reset', time.time() + 3600))
            wait_time = max(0, reset_time - int(time.time())) + 5
            print(f"Rate limit exceeded. Waiting {wait_time} seconds until reset...")
            time.sleep(wait_time)
            user = g.get_user(username)  # Retry after waiting
        else:
            print(f"Error accessing user {username}: {e}")
            return

    broken_links = []
    
    # Process all repositories
    for repo in user.get_repos():
        print(f"Processing repository: {repo.name}")
        try:
            broken_links.extend(crawl_files(repo))
        except Exception as e:
            print(f"Error processing repo {repo.name}: {e}")
    
    # Write results to CSV
    write_to_csv(broken_links, output_file)

if __name__ == "__main__":
    main()