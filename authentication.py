"""
Authentication system for admin panel
"""

from nicegui import ui, app
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from datetime import datetime
from Base import Base
from user import User
from googleSSO import add_google_login_button
from dotenv import load_dotenv

load_dotenv()

# Database setup
engine = create_engine("postgresql://postgres:postgres@localhost/sai_db")
Session = sessionmaker(bind=engine)

# Create users table
Base.metadata.create_all(engine)


def is_authenticated() -> bool:
    """Check if user is authenticated"""
    return app.storage.user.get('authenticated', False)


def get_current_user():
    """Get current logged-in user email"""
    return app.storage.user.get('email')


def get_current_user_role():
    """Get current logged-in user role"""
    return app.storage.user.get('role')


def get_current_user_id():
    """Get current logged-in user ID"""
    return app.storage.user.get('user_id')


def get_current_user_id():
    """Get current logged-in user ID"""
    return app.storage.user.get('user_id')


def require_auth(func):
    """Decorator to require authentication for a page"""
    def wrapper(*args, **kwargs):
        if not is_authenticated():
            ui.navigate.to('/login')
            return
        return func(*args, **kwargs)
    return wrapper


def login_user(email: str, password: str) -> tuple[bool, str]:
    """
    Attempt to log in a user
    Returns: (success: bool, message: str)
    """
    session = Session()
    user = session.query(User).filter_by(email=email).first()
    
    if not user:
        session.close()
        return False, "Invalid email or password"
    
    if not user.is_active:
        session.close()
        return False, "Account is disabled"
    
    if not user.check_password(password):
        session.close()
        return False, "Invalid email or password"
    # Save user data BEFORE closing session
    user_id = user.id
    user_email = user.email
    user_role = user.role
    
    # Update last login
    user.last_login = datetime.utcnow()
    session.commit()
    session.close()
    
    # Store in session AFTER closing (using saved variables)
    app.storage.user['authenticated'] = True
    app.storage.user['user_id'] = user_id
    app.storage.user['email'] = user_email
    app.storage.user['role'] = user_role
    
    return True, "Login successful"


def logout_user():
    """Log out the current user"""
    app.storage.user.clear()


def register_user(email: str, password: str, role: str = 'instructor') -> tuple[bool, str]:
    """
    Register a new user
    Returns: (success: bool, message: str)
    """
    session = Session()
    
    # Check if user already exists
    existing = session.query(User).filter_by(email=email).first()
    if existing:
        session.close()
        return False, "Email already registered"
    
    # Create new user
    user = User(
        email=email,
        password_hash=User.hash_password(password),
        role=role
    )
    session.add(user)
    session.commit()
    session.close()
    
    return True, "Account created successfully"


@ui.page('/login')
def login_page():
    """Login page"""
    
    # If already authenticated, redirect to admin
    if is_authenticated():
        ui.navigate.to('/admin')
        return
    
    with ui.column().classes('w-full h-screen bg-gray-100 flex items-center justify-center'):
        with ui.card().classes('w-full max-w-md p-8'):
            ui.label('Admin Login').classes('text-3xl font-bold mb-6 text-center')
            
            ui.separator().classes('my-0')
            ui.label('Sign in with email').classes('text-sm text-gray-600 text-center')
            
            email_input = ui.input('Email', placeholder='professor@university.edu').classes('w-full')
            password_input = ui.input('Password', password=True, password_toggle_button=True).classes('w-full')
            
            error_label = ui.label('').classes('text-red-600 text-sm mt-2')
            error_label.visible = False
            
            def attempt_login():
                success, message = login_user(email_input.value, password_input.value)
                if success:
                    ui.navigate.to('/admin')
                else:
                    error_label.text = message
                    error_label.visible = True
            
            password_input.on('keydown.enter', attempt_login)
            
            ui.button('Login', on_click=attempt_login).classes('w-full bg-blue-600 text-white mt-4')
            
            ui.separator().classes('my-4')
            add_google_login_button()
            
            ui.label('Need an account?').classes('text-sm text-gray-600 text-center')
            ui.button('Create Account', on_click=lambda: ui.navigate.to('/register')).classes('w-full bg-gray-600 text-white')
            
            ui.button('← Back to Survey', on_click=lambda: ui.navigate.to('/')).classes('w-full bg-gray-400 text-white mt-2')


@ui.page('/register')
def register_page():
    """Registration page"""
    
    with ui.column().classes('w-full h-screen bg-gray-100 flex items-center justify-center'):
        with ui.card().classes('w-full max-w-md p-8'):
            ui.label('Create Account').classes('text-3xl font-bold mb-6 text-center')
            
            email_input = ui.input('Email', placeholder='professor@university.edu').classes('w-full')
            password_input = ui.input('Password', password=True, password_toggle_button=True).classes('w-full')
            password_confirm = ui.input('Confirm Password', password=True, password_toggle_button=True).classes('w-full')
            
            error_label = ui.label('').classes('text-red-600 text-sm mt-2')
            error_label.visible = False
            
            success_label = ui.label('').classes('text-green-600 text-sm mt-2')
            success_label.visible = False
            
            def attempt_register():
                # Validation
                if not email_input.value or '@' not in email_input.value:
                    error_label.text = 'Please enter a valid email'
                    error_label.visible = True
                    return
                
                if len(password_input.value) < 6:
                    error_label.text = 'Password must be at least 6 characters'
                    error_label.visible = True
                    return
                
                if password_input.value != password_confirm.value:
                    error_label.text = 'Passwords do not match'
                    error_label.visible = True
                    return
                
                success, message = register_user(email_input.value, password_input.value)
                if success:
                    success_label.text = message + ' - Redirecting to login...'
                    success_label.visible = True
                    error_label.visible = False
                    ui.timer(2.0, lambda: ui.navigate.to('/login'), once=True)
                else:
                    error_label.text = message
                    error_label.visible = True
            
            ui.button('Create Account', on_click=attempt_register).classes('w-full bg-blue-600 text-white mt-4')
            
            ui.separator().classes('my-4')
            
            ui.button('← Back to Login', on_click=lambda: ui.navigate.to('/login')).classes('w-full bg-gray-400 text-white')


@ui.page('/logout')
def logout_page():
    """Logout page"""
    logout_user()
    ui.navigate.to('/login')