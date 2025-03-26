from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from werkzeug.utils import secure_filename
import pandas as pd
import matplotlib.pyplot as plt
from io import BytesIO
import base64
import os
from datetime import datetime
from models import db, FoodEntry, User
import seaborn as sns
from sqlalchemy import func

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///nutrition.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = 'your-secret-key'
app.config['UPLOAD_FOLDER'] = 'static/uploads'

db.init_app(app)

# Izveidojam datubāzes tabulas
with app.app_context():
    db.create_all()

@app.route('/')
def home():
    return render_template('dashboard.html')

@app.route('/diary', methods=['GET', 'POST'])
def diary():
    if request.method == 'POST':
        date = datetime.strptime(request.form['date'], '%Y-%m-%d').date()
        food_name = request.form['food_name']
        calories = float(request.form['calories'])
        protein = float(request.form['protein'])
        carbs = float(request.form['carbs'])
        fat = float(request.form['fat'])
        
        new_entry = FoodEntry(
            date=date,
            food_name=food_name,
            calories=calories,
            protein=protein,
            carbs=carbs,
            fat=fat,
            user_id=1  # Pagaidām vienkāršs lietotājs
        )
        
        db.session.add(new_entry)
        db.session.commit()
        flash('Pārtikas ieraksts veiksmīgi pievienots!', 'success')
        return redirect(url_for('diary'))
    
    # Iegūstam visus ierakstus
    entries = FoodEntry.query.order_by(FoodEntry.date.desc()).all()
    return render_template('diary.html', entries=entries)

@app.route('/delete_entry/<int:id>', methods=['POST'])
def delete_entry(id):
    entry = FoodEntry.query.get_or_404(id)
    db.session.delete(entry)
    db.session.commit()
    flash('Ieraksts veiksmīgi dzēsts!', 'success')
    return redirect(url_for('diary'))

@app.route('/dashboard')
def dashboard():
    # Datu apkopojumi
    total_entries = FoodEntry.query.count()
    avg_calories = db.session.query(func.avg(FoodEntry.calories)).scalar()
    
    # 7 pēdējo dienu dati
    last_week = db.session.query(
        FoodEntry.date,
        func.sum(FoodEntry.calories).label('total_calories'),
        func.sum(FoodEntry.protein).label('total_protein'),
        func.sum(FoodEntry.carbs).label('total_carbs'),
        func.sum(FoodEntry.fat).label('total_fat')
    ).group_by(FoodEntry.date).order_by(FoodEntry.date.desc()).limit(7).all()
    
    # Pārveidojam datus vizualizācijai
    dates = [entry.date.strftime('%Y-%m-%d') for entry in last_week][::-1]
    calories = [entry.total_calories for entry in last_week][::-1]
    protein = [entry.total_protein for entry in last_week][::-1]
    carbs = [entry.total_carbs for entry in last_week][::-1]
    fat = [entry.total_fat for entry in last_week][::-1]
    
    # Kaloriju grafiks
    plt.figure(figsize=(10, 5))
    plt.plot(dates, calories, marker='o', color='orange')
    plt.title('Kaloriju patēriņš pēdējās 7 dienās')
    plt.xlabel('Datums')
    plt.ylabel('Kalorijas')
    plt.xticks(rotation=45)
    plt.tight_layout()
    calories_plot = get_plot_url(plt)
    plt.close()
    
    # Makroelementu grafiks
    plt.figure(figsize=(10, 5))
    plt.bar(dates, protein, label='Olbaltumvielas', color='blue')
    plt.bar(dates, carbs, bottom=protein, label='Ogļhidrāti', color='green')
    plt.bar(dates, fat, bottom=[p+c for p,c in zip(protein, carbs)], label='Tauki', color='red')
    plt.title('Makroelementu sadalījums pēdējās 7 dienās')
    plt.xlabel('Datums')
    plt.ylabel('Grami')
    plt.legend()
    plt.xticks(rotation=45)
    plt.tight_layout()
    macros_plot = get_plot_url(plt)
    plt.close()
    
    # Populārākie ēdieni
    top_foods = db.session.query(
        FoodEntry.food_name,
        func.count(FoodEntry.id).label('count')
    ).group_by(FoodEntry.food_name).order_by(func.count(FoodEntry.id).desc()).limit(5).all()
    
    food_names = [food[0] for food in top_foods]
    food_counts = [food[1] for food in top_foods]
    
    plt.figure(figsize=(8, 8))
    plt.pie(food_counts, labels=food_names, autopct='%1.1f%%', startangle=140)
    plt.title('Populārākie ēdieni')
    top_foods_plot = get_plot_url(plt)
    plt.close()
    
    return render_template('dashboard.html', 
                         total_entries=total_entries,
                         avg_calories=round(avg_calories, 2) if avg_calories else 0,
                         calories_plot=calories_plot,
                         macros_plot=macros_plot,
                         top_foods_plot=top_foods_plot)

@app.route('/reports')
def reports():
    # Makroelementu sadalījums
    total_protein = db.session.query(func.sum(FoodEntry.protein)).scalar() or 0
    total_carbs = db.session.query(func.sum(FoodEntry.carbs)).scalar() or 0
    total_fat = db.session.query(func.sum(FoodEntry.fat)).scalar() or 0
    
    # Makroelementu sadalījuma vizualizācija
    labels = ['Olbaltumvielas', 'Ogļhidrāti', 'Tauki']
    sizes = [total_protein, total_carbs, total_fat]
    
    plt.figure(figsize=(8, 8))
    plt.pie(sizes, labels=labels, autopct='%1.1f%%', startangle=140)
    plt.title('Kopējais makroelementu sadalījums')
    macros_pie = get_plot_url(plt)
    plt.close()
    
    # Kaloriju sadalījums pa dienām
    daily_calories = db.session.query(
        FoodEntry.date,
        func.sum(FoodEntry.calories).label('total_calories')
    ).group_by(FoodEntry.date).order_by(FoodEntry.date).all()
    
    dates = [entry.date.strftime('%Y-%m-%d') for entry in daily_calories]
    calories = [entry.total_calories for entry in daily_calories]
    
    plt.figure(figsize=(12, 6))
    sns.barplot(x=dates, y=calories, palette='viridis')
    plt.title('Kaloriju patēriņš pa dienām')
    plt.xlabel('Datums')
    plt.ylabel('Kalorijas')
    plt.xticks(rotation=45)
    plt.tight_layout()
    daily_calories_plot = get_plot_url(plt)
    plt.close()
    
    # Kaloriju histogramma
    plt.figure(figsize=(10, 6))
    sns.histplot([entry.calories for entry in FoodEntry.query.all()], bins=15, kde=True)
    plt.title('Kaloriju sadalījums pa ēdieniem')
    plt.xlabel('Kalorijas')
    plt.ylabel('Skaits')
    calories_hist = get_plot_url(plt)
    plt.close()
    
    return render_template('reports.html',
                         macros_pie=macros_pie,
                         daily_calories_plot=daily_calories_plot,
                         calories_hist=calories_hist)

@app.route('/import', methods=['GET', 'POST'])
def import_data():
    if request.method == 'POST':
        if 'file' not in request.files:
            flash('Nav izvēlēts fails', 'error')
            return redirect(request.url)
        
        file = request.files['file']
        if file.filename == '':
            flash('Nav izvēlēts fails', 'error')
            return redirect(request.url)
        
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(filepath)
            
            try:
                df = pd.read_csv(filepath)
                
                # Pārbaudam, vai ir nepieciešamās kolonnas
                required_columns = ['date', 'food_name', 'calories', 'protein', 'carbs', 'fat']
                if not all(col in df.columns for col in required_columns):
                    flash('CSV failam jāsatur kolonnas: date, food_name, calories, protein, carbs, fat', 'error')
                    return redirect(request.url)
                
                # Importējam datus
                imported = 0
                for _, row in df.iterrows():
                    try:
                        new_entry = FoodEntry(
                            date=datetime.strptime(row['date'], '%Y-%m-%d').date(),
                            food_name=row['food_name'],
                            calories=float(row['calories']),
                            protein=float(row['protein']),
                            carbs=float(row['carbs']),
                            fat=float(row['fat']),
                            user_id=1
                        )
                        db.session.add(new_entry)
                        imported += 1
                    except Exception as e:
                        print(f"Kļūda importējot rindu: {e}")
                        continue
                
                db.session.commit()
                flash(f'Veiksmīgi importēti {imported} ieraksti!', 'success')
                return redirect(url_for('diary'))
            
            except Exception as e:
                flash(f'Kļūda importējot datus: {str(e)}', 'error')
                return redirect(request.url)
        
        else:
            flash('Atļauts tikai CSV failu augšupielāde', 'error')
            return redirect(request.url)
    
    return render_template('import.html')

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() == 'csv'

def get_plot_url(plt):
    # Konvertējam grafiku uz base64 attēlu
    buffer = BytesIO()
    plt.savefig(buffer, format='png')
    buffer.seek(0)
    image_base64 = base64.b64encode(buffer.getvalue()).decode('utf-8')
    return f"data:image/png;base64,{image_base64}"

if __name__ == '__main__':
    app.run(debug=True)