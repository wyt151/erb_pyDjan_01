import os
import csv
import json
import sys
from typing import Dict, Any, List, Tuple
import django
from django.db import connection
from django.apps import apps
from django.db.utils import OperationalError
from contextlib import contextmanager
from datetime import datetime, date, time
from decimal import Decimal

# Database configuration
DB_CONFIG = {
    'ENGINE': 'django.db.backends.postgresql',
    'NAME': 'your_db_name',
    'USER': 'your_db_user',
    'PASSWORD': 'your_db_password',
    'HOST': 'localhost',
    'PORT': '5432',
}

class CustomJSONEncoder(json.JSONEncoder):
    """Custom JSON encoder to handle datetime, date, time, and Decimal objects"""
    def default(self, obj):
        if isinstance(obj, (datetime, date)):
            return obj.isoformat()
        elif isinstance(obj, time):
            return obj.isoformat()
        elif isinstance(obj, Decimal):
            return float(obj)
        return super().default(obj)

def validate_file_type(file_path: str) -> Tuple[bool, str]:
    """Validate if file is CSV or JSON"""
    if not file_path.lower().endswith(('.csv', '.json')):
        return False, "Error: Only CSV and JSON files are supported"
    return True, ""

def get_file_headers(file_path: str) -> Tuple[List[str], str]:
    """Get file headers from CSV or JSON"""
    try:
        if file_path.lower().endswith('.csv'):
            with open(file_path, 'r') as file:
                reader = csv.reader(file)
                return next(reader), "csv"
        else:  # JSON
            with open(file_path, 'r') as file:
                data = json.load(file)
                if isinstance(data, list) and len(data) > 0:
                    return list(data[0].keys()), "json"
                return [], "json"
    except Exception as e:
        return [], f"Error reading file: {str(e)}"

@contextmanager
def db_cursor():
    """Context manager for database cursor"""
    cursor = connection.cursor()
    try:
        yield cursor
    finally:
        cursor.close()
        connection.close()

def check_database_connection() -> tuple[bool, str]:
    """Check if database connection is successful"""
    try:
        with db_cursor() as cursor:
            cursor.execute("SELECT 1")
        return True, "Database connection successful"
    except OperationalError as e:
        return False, f"Database connection failed: {str(e)}"

def setup_django():
    """Setup Django environment"""
    # Get the project root directory (assuming script is in project folder)
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    
    # Add project root to Python path
    sys.path.append(project_root)
    
    # Set Django settings module
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'bcre.settings')
    
    # Initialize Django
    django.setup()

def check_file_exists(file_path: str) -> bool:
    """Check if file exists"""
    return os.path.exists(file_path)

def check_table_exists(table_name: str) -> bool:
    """Check if table exists in database"""
    with db_cursor() as cursor:
        cursor.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_name = %s
            );
        """, [table_name])
        return cursor.fetchone()[0]

def get_table_columns(table_name: str, include_id: bool = True) -> List[str]:
    """Get table column names, optionally including id column"""
    with db_cursor() as cursor:
        cursor.execute("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = %s
            ORDER BY ordinal_position;
        """, [table_name])
        columns = [row[0] for row in cursor.fetchall()]
        if not include_id and 'id' in columns:
            columns.remove('id')
        return columns

def clean_table(table_name: str):
    """Delete all records from table and reset primary key sequence"""
    with db_cursor() as cursor:
        # Delete all records
        cursor.execute(f"DELETE FROM {table_name};")
        # Reset primary key sequence
        cursor.execute(f"ALTER SEQUENCE {table_name}_id_seq RESTART WITH 1;")

def import_file_to_db(file_path: str, table_name: str) -> str:
    """Import CSV or JSON data to database table"""
    try:
        # Check file existence
        if not check_file_exists(file_path):
            return f"Error: File {file_path} does not exist"

        # Validate file type
        is_valid, error_msg = validate_file_type(file_path)
        if not is_valid:
            return error_msg

        # Check table existence
        if not check_table_exists(table_name):
            return f"Error: Table {table_name} does not exist"

        # Get file headers and type
        headers, file_type = get_file_headers(file_path)
        if not headers:
            return "Error: Could not read file headers"

        has_id_column = 'id' in headers

        # Get table columns (excluding id if file doesn't have it)
        table_columns = get_table_columns(table_name, include_id=has_id_column)

        # Check format compatibility
        if set(headers) != set(table_columns):
            return f"Error: File format does not match table structure. Expected columns: {table_columns}, Found: {headers}"

        # Clean existing data
        clean_table(table_name)

        # Import data
        with db_cursor() as cursor:
            if file_type == "csv":
                with open(file_path, 'r') as file:
                    reader = csv.DictReader(file)
                    for row in reader:
                        columns = ', '.join(row.keys())
                        values = ', '.join(['%s'] * len(row))
                        query = f"INSERT INTO {table_name} ({columns}) VALUES ({values})"
                        cursor.execute(query, list(row.values()))
            else:  # JSON
                with open(file_path, 'r') as file:
                    data = json.load(file)
                    for row in data:
                        columns = ', '.join(row.keys())
                        values = ', '.join(['%s'] * len(row))
                        query = f"INSERT INTO {table_name} ({columns}) VALUES ({values})"
                        cursor.execute(query, list(row.values()))

        return f"Successfully imported {file_path} to {table_name}"

    except Exception as e:
        return f"Error during import: {str(e)}"

def export_db_to_file(table_name: str, file_path: str) -> str:
    """Export database table to CSV or JSON"""
    try:
        # Validate file type
        is_valid, error_msg = validate_file_type(file_path)
        if not is_valid:
            return error_msg

        # Check table existence
        if not check_table_exists(table_name):
            return f"Error: Table {table_name} does not exist"

        # Check if file exists and ask for confirmation
        if check_file_exists(file_path):
            response = input(f"File {file_path} already exists. Do you want to replace it? (y/n): ")
            if response.lower() != 'y':
                return "Export cancelled"

        # Get table columns (including id)
        table_columns = get_table_columns(table_name, include_id=True)

        # Export data
        with db_cursor() as cursor:
            cursor.execute(f"SELECT {', '.join(table_columns)} FROM {table_name}")
            rows = cursor.fetchall()

        if file_path.lower().endswith('.csv'):
            with open(file_path, 'w', newline='') as file:
                writer = csv.writer(file)
                writer.writerow(table_columns)  # Write headers in table order
                writer.writerows(rows)
        else:  # JSON
            data = []
            for row in rows:
                # Convert row to dict and handle special types
                row_dict = {}
                for i, value in enumerate(row):
                    if isinstance(value, (datetime, date, time, Decimal)):
                        if isinstance(value, datetime):
                            row_dict[table_columns[i]] = value.isoformat()
                        elif isinstance(value, date):
                            row_dict[table_columns[i]] = value.isoformat()
                        elif isinstance(value, time):
                            row_dict[table_columns[i]] = value.isoformat()
                        elif isinstance(value, Decimal):
                            row_dict[table_columns[i]] = float(value)
                    else:
                        row_dict[table_columns[i]] = value
                data.append(row_dict)
            
            with open(file_path, 'w') as file:
                json.dump(data, file, indent=4, cls=CustomJSONEncoder)

        return f"Successfully exported {table_name} to {file_path}"

    except Exception as e:
        return f"Error during export: {str(e)}"

def main():
    """Main function to handle user input and execute commands"""
    setup_django()
    
    # Check database connection first
    connection_ok, message = check_database_connection()
    if not connection_ok:
        print(f"Error: {message}")
        print("Please check your database configuration and try again.")
        return

    while True:
        print("\nDatabase File Manager")
        print("1. Import File to Database")
        print("2. Export Database to File")
        print("3. Exit")
        
        choice = input("\nEnter your choice (1-3): ")

        if choice == '1':
            file_path = input("Enter file path (CSV or JSON): ")
            table_name = input("Enter table name: ")
            result = import_file_to_db(file_path, table_name)
            print(result)

        elif choice == '2':
            table_name = input("Enter table name: ")
            file_path = input("Enter file path (CSV or JSON): ")
            result = export_db_to_file(table_name, file_path)
            print(result)

        elif choice == '3':
            print("Goodbye!")
            break

        else:
            print("Invalid choice. Please try again.")

if __name__ == "__main__":
    main() 