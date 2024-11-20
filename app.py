from flask import Flask, render_template, request, redirect, url_for, flash, session
import os
from flask_sqlalchemy import SQLAlchemy
from scripts.azure_vm_manager import create_vm1, stop_vm, start_vm # Import the VM management function
from scripts.deployment import deploy_website  # Import the deployment function
from flask_login import LoginManager, current_user, login_user, logout_user, login_required
from werkzeug.utils import secure_filename
from flask import jsonify
from datetime import datetime


app = Flask(__name__)
app.secret_key = 'your_secret_key_here'

UPLOAD_FOLDER = 'uploads'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///clients.db'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER


Client_login_manager = LoginManager()
Client_login_manager.init_app(app)

# Ensure the upload folder exists
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

db = SQLAlchemy(app)

class Client(db.Model):
    __tablename__ = 'clients'  # Table name for the Client model
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(150), unique=True, nullable=False)
    password = db.Column(db.String(150), nullable=False)
    vms = db.relationship('VM', backref='client', lazy=True)

    def __repr__(self) -> str:
        return f"{self.username} - {self.password}"

    def is_authenticated(self):
        return True

    def is_active(self):
        return True
    
    def is_anonymous(self):
        return False
    
    def get_id(self):
        return str(self.id)  # Return the ID as a string

class VM(db.Model):
    __tablename__ = 'vms'  # Table name for the VM model
    id = db.Column(db.Integer, primary_key=True)
    vm_name = db.Column(db.String(100), nullable=False)
    public_ip = db.Column(db.String(100), nullable=False)
    client_id = db.Column(db.Integer, db.ForeignKey('clients.id'), nullable=False)  # Reference the 'clients' table
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    resource_group_name = db.Column(db.String(100), nullable=False)  # Column for resource group name
    username = db.Column(db.String(100), nullable=False)  # Column for VM username
    password = db.Column(db.String(100), nullable=False)
    status = db.Column(db.String(100), nullable=True)  # New column to store VM status (running, stopped, etc.)

@app.route('/')
def index():
    return render_template('index.html')


@app.route('/client/register', methods=['GET', 'POST'])
def client_register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        new_user = Client(username=username, password=password)
        db.session.add(new_user)
        db.session.commit()
        return redirect(url_for('client_login'))  
    return render_template('client_register.html')


@Client_login_manager.user_loader
def load_user(user_id):
    # Flask-Login will call this to load the user
    return Client.query.get(int(user_id))

@app.route('/client/login', methods=['GET', 'POST'])
def client_login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = Client.query.filter_by(username=username).first()

        if user:
            if user.password == password:
                # Log the user in
                login_user(user)
                flash(f'Welcome, {user.username}!', 'success')
                return redirect(url_for('dashboard'))  # Redirect to dashboard
            else:
                # Incorrect password
                flash('Incorrect password. Please try again.', 'danger')
        else:
            # User not found
            flash('User not found. Please register first.', 'danger')

    return render_template('client_login.html')


@app.route('/client/login/dashboard')
@login_required
def dashboard():
    # You can add whatever logic you want to display on the dashboard
    return render_template('dashboard.html', username=current_user.username)  # Make sure you have a 'dashboard.html' template


@app.route('/client/login/dashboard/create-vm', methods=['GET'])
@login_required
def create_vm_initial():
    # Render the form for selecting resource group name and location
    return render_template('create_vm_initial.html')

@app.route('/client/login/dashboard/create-vm/', methods=['POST'])
@login_required
def create_vm_final():

    resource_group_name = request.form['resource_group_name']
    location = request.form['location']

    subscription_id = "7eed0ac8-1912-4c99-af68-720b126c8599"
    public_ip, vm_username, vm_password, vm_name = create_vm1(subscription_id, resource_group_name, location)
    

    
    if public_ip:

        # # Store VM credentials and public IP in the session for deployment
        # session['vm_public_ip'] = public_ip
        # session['vm_username'] = vm_username
        # session['vm_password'] = vm_password

        # Create a new VM record in the database
        new_vm = VM(public_ip=public_ip, client_id=current_user.id, username = vm_username, password = vm_password, resource_group_name = resource_group_name, vm_name = vm_name, status='Running')
        db.session.add(new_vm)
        db.session.commit()  # Commit the transaction to save it to the database
        
        # Flash the success message and redirect to the result page with the public IP
        flash(f"VM created successfully! Public IP: {public_ip}")
        return redirect(url_for('vm_created', public_ip=public_ip, username=vm_username, password=vm_password))
    else:
        flash("Failed to create VM.")
        return redirect(url_for('dashboard'))




# @app.route('/create-vm/vm-created/<public_ip>', methods=['GET'])
# def vm_created(public_ip):
#     return render_template('vm_created.html', public_ip=public_ip)

@app.route('/create-vm/vm-created/<public_ip>', methods=['GET', 'POST'])
def vm_created(public_ip):

    vm_username = request.args.get('username')
    vm_password = request.args.get('password')

    print(f"retrieved the admin username: {vm_username}")
    print(f"retrieved the admin password: {vm_password}")

    if request.method == 'POST':
        # Ensure the folder was uploaded
        if 'website_folder' not in request.files:
            flash("No folder selected for upload.")
            return redirect(request.url)

        uploaded_files = request.files.getlist('website_folder')

        # Validate uploaded files
        if not uploaded_files or all(f.filename == '' for f in uploaded_files):
            flash("No files were uploaded or filenames are missing.")
            return redirect(request.url)

        # Save the uploaded files, preserving folder structure
        for website_file in uploaded_files:
            if website_file.filename == '':
                flash("One of the selected files has no filename.")
                return redirect(request.url)

            # Ensure directories are created before saving files
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], secure_filename(website_file.filename))
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            website_file.save(file_path)

        # Deploy the entire folder to the VM
        try:
            deploy_website(public_ip, app.config['UPLOAD_FOLDER'], vm_username, vm_password)
            flash(f"Website hosted successfully on VM with Public IP: {public_ip}")
            return redirect(url_for('website_success', public_ip=public_ip))
        except Exception as e:
            flash(f"Error deploying website: {e}")
            return redirect(request.url)

    return render_template('vm_created.html', public_ip=public_ip, username=vm_username, password=vm_password)


@app.route('/website_success/<public_ip>')
def website_success(public_ip):
    website_url = f"http://{public_ip}"
    return render_template('website_success.html', public_ip=public_ip, website_url=website_url)


@app.route('/client/login/dashboard/vm-list/', methods=['GET'])
@login_required
def list_vms():
    # Fetch all VMs created by the currently logged-in client
    client_vms = VM.query.filter_by(client_id=current_user.id).all()

    # Render the VM list template
    return render_template('vm_list.html', vms=client_vms)


@app.route('/client/login/dashboard/vm-list/stop/<int:vm_id>', methods=['POST'])
@login_required
def stop_vm_route(vm_id):
    # Fetch the VM object from the database using the VM ID
    vm = VM.query.get(vm_id)
    if not vm or vm.client_id != current_user.id:
        flash("VM not found or access denied.", "danger")
        return redirect(url_for('list_vms'))

    # Call the stop_vm function with the VM's details
    resource_group_name = vm.resource_group_name  # Ensure this column exists in your VM model
    vm_name = vm.vm_name  # Example VM name generation

    try:
        stop_vm(resource_group_name, vm_name)
        flash(f"VM {vm_name} has been stopped successfully.", "success")

        vm.status = 'stopped'  # Change the status to 'stopped'
        db.session.commit()

        return redirect(url_for('vm_stopped', vm_name=vm_name))
    except Exception as e:
        flash(f"Failed to stop VM {vm_name}: {str(e)}", "danger")

    return redirect(url_for('list_vms'))


@app.route('/client/login/dashboard/vm-list/start/<int:vm_id>', methods=['POST'])
@login_required
def start_vm_route(vm_id):
    # Fetch the VM object from the database using the VM ID
    vm = VM.query.get(vm_id)
    if not vm or vm.client_id != current_user.id:
        flash("VM not found or access denied.", "danger")
        return redirect(url_for('list_vms'))

    # Call the stop_vm function with the VM's details
    resource_group_name = vm.resource_group_name  # Ensure this column exists in your VM model
    vm_name = vm.vm_name  # Example VM name generation

    try:
        start_vm(resource_group_name, vm_name)
        flash(f"VM {vm_name} has been started successfully.", "success")
        
        vm.status = 'Running'  # Change the status to 'stopped'
        db.session.commit()

        return redirect(url_for('vm_restarted', vm_name=vm_name))
    except Exception as e:
        flash(f"Failed to stop VM {vm_name}: {str(e)}", "danger")

    return redirect(url_for('list_vms'))

@app.route('/client/login/dashboard/vm-stopped/<vm_name>', methods=['GET'])
@login_required
def vm_stopped(vm_name):
    return render_template('vm_stopped.html', vm_name=vm_name)


@app.route('/client/login/dashboard/vm-restarted/<vm_name>', methods=['GET'])
@login_required
def vm_restarted(vm_name):
    return render_template('vm_restarted.html', vm_name=vm_name)

@app.route('/client/login/dashboard/host_website/', methods=['GET'])
@login_required
def host_website():
    # Fetch all VMs created by the currently logged-in client
    client_vms = VM.query.filter_by(client_id=current_user.id).all()

    # Render the VM list template
    return render_template('host_website.html', vms=client_vms)
   

@app.route('/client/login/dashboard/host_website/host_website_on/<int:vm_id>', methods=['POST'])
@login_required
def host_website_on(vm_id):
    # Fetch the VM object from the database using the VM ID
    vm = VM.query.get(vm_id)
    if not vm or vm.client_id != current_user.id:
        flash("VM not found or access denied.", "danger")
        return redirect(url_for('host_website'))


    return redirect(url_for('vm_created', public_ip=vm.public_ip, username=vm.username, password=vm.password))



if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)
