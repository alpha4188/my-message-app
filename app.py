from flask import Flask, render_template, request, redirect, url_for, send_file
import csv
import random
import os
import math
import re
from typing import List, Dict, Tuple
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['ALLOWED_EXTENSIONS'] = {'csv'}

# Ensure upload folder exists
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

def standardize_phone(phone: str) -> str:
    """Standardize phone number format by removing all non-digits."""
    return re.sub(r'\D', '', str(phone))

def read_dnc_list(file_path: str) -> set:
    """Read DNC numbers from CSV file and return as a set."""
    dnc_numbers = set()
    if not file_path:
        return dnc_numbers
        
    try:
        with open(file_path, 'r', encoding='utf-8') as file:
            reader = csv.reader(file)
            for row in reader:
                if row:
                    phone = standardize_phone(row[0])
                    if phone and not phone.lower() in ['phone', 'telephone', 'number']:
                        dnc_numbers.add(phone)
        return dnc_numbers
    except FileNotFoundError:
        print(f"Warning: DNC file '{file_path}' not found.")
        return dnc_numbers
    except Exception as e:
        print(f"Error processing DNC file: {str(e)}")
        return dnc_numbers

def identify_fields(headers: List[str]) -> Tuple[List[str], str, str]:
    phone_fields = [field for field in headers if field in ['phone_1', 'phone_2', 'phone_3']]
    name_field = 'first_name' if 'first_name' in headers else ''
    address_field = 'associated_property_address_line_1' if 'associated_property_address_line_1' in headers else ''
    return phone_fields, name_field, address_field

def is_valid_phone(phone: str) -> bool:
    if not phone:
        return False
    
    if "landline excluded" in str(phone).lower():
        return False
    
    phone = standardize_phone(phone)
    return len(phone) >= 7 and len(phone) <= 15

def parse_spintax(text: str) -> str:
    while '[' in text:
        start = text.find('[')
        end = text.find(']', start)
        if end == -1:
            break
        
        options = text[start+1:end].split('/')
        replacement = random.choice(options)
        text = text[:start] + replacement + text[end+1:]
    return text

def read_templates(file_path: str) -> List[str]:
    templates = []
    try:
        with open(file_path, 'r', encoding='utf-8') as file:
            reader = csv.reader(file)
            for row in reader:
                if row:
                    templates.extend(row)
    except FileNotFoundError:
        print(f"Error: Template file '{file_path}' not found.")
        return []
    return templates

def generate_messages(contacts_file: str, template_file: str, dnc_file: str = None) -> Tuple[List[Dict], int, int]:
    messages = []
    templates = read_templates(template_file)
    blocked_count = 0
    
    if not templates:
        return messages

    try:
        with open(contacts_file, 'r', encoding='utf-8') as file:
            reader = csv.DictReader(file)
            all_rows = list(reader)
            random.shuffle(all_rows)
            
            headers = reader.fieldnames
            
            if not headers:
                print("Error: CSV file is empty or has no headers.")
                return messages
            
            phone_fields, name_field, address_field = identify_fields(headers)
            
            if not phone_fields:
                print("Error: Required phone fields (phone_1, phone_2, phone_3) not found in CSV.")
                return messages
            
            if not name_field:
                print("Error: Required field 'first_name' not found in CSV.")
                return messages
            
            if not address_field:
                print("Error: Required field 'associated_property_address_line_1' not found in CSV.")
                return messages
            
            dnc_numbers = read_dnc_list(dnc_file) if dnc_file else set()
            
            for row in all_rows:
                phones = []
                for field in phone_fields:
                    phone = row.get(field, '').strip()
                    if is_valid_phone(phone):
                        phones.append(phone)
                
                name = row.get(name_field, '').strip()
                address = row.get(address_field, '').strip()
                
                for phone in phones:
                    if standardize_phone(phone) in dnc_numbers:
                        blocked_count += 1
                        continue
                        
                    template = random.choice(templates)
                    message = template.replace('{name}', name).replace('{address}', address)
                    message = parse_spintax(message)
                    messages.append({'phone': phone, 'message': message})
                    
    except FileNotFoundError:
        print(f"Error: Contacts file '{contacts_file}' not found.")
    except Exception as e:
        print(f"Error processing file: {str(e)}")
    
    random.shuffle(messages)
    return messages, len(messages), blocked_count

from datetime import datetime

def save_messages(messages: List[Dict], output_file: str):
    today = datetime.now().strftime('%m-%d-%Y')
    output_file = f"{today}-Messages.csv"
    output_path = os.path.join(app.config['UPLOAD_FOLDER'], output_file)
    with open(output_path, 'w', newline='', encoding='utf-8') as file:
        writer = csv.writer(file, delimiter=',', quoting=csv.QUOTE_MINIMAL)
        for msg in messages:
            if not msg['phone'].lower() in ['phone', 'telephone', 'number']:
                phone = standardize_phone(msg['phone'])
                writer.writerow([phone, msg['message']])
    return output_file

def split_file(input_file: str, messages_per_file: int):
    messages = []
    input_path = os.path.join(app.config['UPLOAD_FOLDER'], input_file)
    with open(input_path, 'r', encoding='utf-8') as file:
        reader = csv.reader(file, delimiter=',')
        messages = [
            row for row in reader 
            if not row[0].lower() in ['phone', 'telephone', 'number']
        ]
    
    total_messages = len(messages)
    num_files = math.ceil(total_messages / messages_per_file)
    today = datetime.now().strftime('%m-%d-%Y')
    
    output_files = []
    for i in range(num_files):
        start_idx = i * messages_per_file
        end_idx = min((i + 1) * messages_per_file, total_messages)
        
        output_filename = f"{today}-Messages-Part-{i+1}.csv"
        output_path = os.path.join(app.config['UPLOAD_FOLDER'], output_filename)
        with open(output_path, 'w', newline='', encoding='utf-8') as file:
            writer = csv.writer(file, delimiter=',', quoting=csv.QUOTE_MINIMAL)
            writer.writerows(messages[start_idx:end_idx])
        output_files.append(output_filename)
    return output_files

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/generate', methods=['POST'])
def generate():
    if 'contacts' not in request.files or 'templates' not in request.files:
        return redirect(url_for('index'))
        
    contacts_file = request.files['contacts']
    templates_file = request.files['templates']
    dnc_file = request.files.get('dnc')
    
    if contacts_file.filename == '' or templates_file.filename == '':
        return redirect(url_for('index'))
        
    if contacts_file and allowed_file(contacts_file.filename) and \
       templates_file and allowed_file(templates_file.filename):
        
        contacts_path = os.path.join(app.config['UPLOAD_FOLDER'], secure_filename(contacts_file.filename))
        templates_path = os.path.join(app.config['UPLOAD_FOLDER'], secure_filename(templates_file.filename))
        dnc_path = os.path.join(app.config['UPLOAD_FOLDER'], secure_filename(dnc_file.filename)) if dnc_file else None
        
        contacts_file.save(contacts_path)
        templates_file.save(templates_path)
        if dnc_file:
            dnc_file.save(dnc_path)
        
        messages, messages_created, messages_blocked = generate_messages(contacts_path, templates_path, dnc_path)
        
        output_file = save_messages(messages, os.path.join(app.config['UPLOAD_FOLDER'], 'messages.csv'))
        
        if request.form.get('split') == 'yes':
            try:
                messages_per_file = int(request.form.get('messages_per_file', 1000))
                output_files = split_file(output_file, messages_per_file)
                return render_template('download.html', 
                    files=output_files,
                    messages_created=messages_created,
                    messages_blocked=messages_blocked
                )
            except ValueError:
                pass
                
        return render_template('download.html', 
            files=[output_file],
            messages_created=messages_created,
            messages_blocked=messages_blocked
        )
        
    return redirect(url_for('index'))

@app.route('/download/<filename>')
def download(filename):
    return send_file(os.path.join(app.config['UPLOAD_FOLDER'], filename), as_attachment=True)

if __name__ == '__main__':
    app.run(debug=True)
