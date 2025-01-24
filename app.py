import sqlite3
import re
import tensorflow as tf
from tensorflow.keras.preprocessing import image # type: ignore
import numpy as np
import os
from flask import Flask, request, render_template, redirect, url_for, session , flash
from werkzeug.security import check_password_hash
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = 'supersecretkey'  # Oturum yönetimi için gerekli

# Veritabanı bağlantısını oluşturma
def get_db_connection():
    conn = sqlite3.connect('patient.db')  # Veritabanı dosyanızın adı
    conn.row_factory = sqlite3.Row  # Kolonları sözlük olarak almak için
    return conn

model = tf.keras.models.load_model('models_ckpt.keras')

# Model ile tahmin yapacak fonksiyon
def predict_disease(image_path):
    # Resmi yükleme ve boyutlandırma
    img = image.load_img(image_path, target_size=(224, 224))  # Modelin beklediği boyut
    img_array = image.img_to_array(img)  # Resmi array'e dönüştürme
    img_array = np.expand_dims(img_array, axis=0)  # Batch boyutunu ekleme
    
    # Model ile tahmin yapma
    prediction = model.predict(img_array)
    predicted_class = np.argmax(prediction, axis=-1)[0]  # Tahmin edilen sınıfı al

    # Sınıf etiketine göre açıklama yapma
    class_labels = ["Kanser", "Crohn", "Normal", "Polip", "Ulcerative"]  # Modelin sınıf etiketleri
    result = class_labels[predicted_class]  # Tahmin edilen sınıf etiketini al

    return result

@app.route('/predict', methods=['GET', 'POST'])
def predict():
    result = None  # Tahmin sonucu başlangıçta boş
    if request.method == 'POST':
        # Dosya yükleme işlemi
        if 'file' not in request.files:
            flash('Dosya seçilmedi!', 'danger')
            return redirect(request.url)
        
        file = request.files['file']
        
        if file.filename == '':
            flash('Dosya seçilmedi!', 'danger')
            return redirect(request.url)
        
        if file:
            # Dosyayı kaydetmek için güvenli bir isim oluşturuyoruz
            filename = secure_filename(file.filename)
            file_path = os.path.join('uploads', filename)  # 'uploads' klasörüne kaydedilecek
            file.save(file_path)  # Dosyayı kaydediyoruz
            
            # Model ile tahmin yapma
            result = predict_disease(file_path)  # Tahmin işlemi
            session['disease_result'] = result  # Sonucu session'a kaydet

            # Sınıflara göre dosyayı kaydetme işlemi
            class_labels = ["Kanser", "Crohn", "Normal", "Polip", "Ulcerative"]  # Modelin sınıf etiketleri
            predicted_class = result  # Tahmin edilen hastalık sınıfı

            # Yolu oluşturun, sınıf ismine göre klasör yapısı
            class_folder = os.path.join('uploads', predicted_class)
            if not os.path.exists(class_folder):
                os.makedirs(class_folder)  # Klasör yoksa oluştur

            # Dosyayı sınıf klasörüne taşı
            new_file_path = os.path.join(class_folder, filename)
            os.rename(file_path, new_file_path)  # Dosyayı taşıyoruz
        return redirect(url_for('home'))
    return render_template('predict.html', user=session.get('user'), result=result)


@app.route('/', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        
        # Veritabanına bağlan
        conn = get_db_connection()
        
        # E-posta ile kullanıcıyı sorgula
        user = conn.execute('SELECT * FROM kullanicilar WHERE eposta = ?', (email,)).fetchone()
        
        # Eğer kullanıcı varsa ve parola doğruysa
        if user and user['parola'] == password:  # Burada parolayı hash yerine düz metinle karşılaştırıyoruz
            # Giriş başarılı, oturum aç
            session['user'] = {'id': user['id'], 'name': user['ad'], 'surname': user['soyad']}
            conn.close()  # Bağlantıyı kapat
            return redirect(url_for('home'))  # Home sayfasına yönlendirme
        else:
            # Hata mesajı ile tekrar login sayfasına dön
            conn.close()  # Bağlantıyı kapat
            return render_template('login.html', error="E-posta adresi veya parola hatalı.")
    
    return render_template('login.html')


@app.route('/home')
def home():
    # Kullanıcı oturumu kontrol et
    if 'user' not in session:  
        return redirect(url_for('login'))
    
    user = session['user']
    return render_template('index.html', user=user)

@app.route('/kaydet', methods=['POST'])
def kaydet():
    if request.method == 'POST':
        # Formdan gelen verileri alıyoruz
        name = request.form['name']
        surname = request.form['surname']
        tckn = request.form['tckn']
        teshis = request.form['teshis']
        
        # Hata mesajlarını tutacak bir dict oluşturuyoruz
        errors = {}

        # Ad alanının kontrolü
        if not name:
            errors['name'] = 'Lütfen hasta adını giriniz.'
        
        # Soyad alanının kontrolü
        if not surname:
            errors['surname'] = 'Lütfen hasta soyadını giriniz.'
        
        # TC No'nun doğruluğunu kontrol et (sadece rakam ve 11 haneli olmalı)
        if not re.match(r'^\d{11}$', tckn):
            errors['tckn'] = 'Lütfen geçerli bir TC no giriniz (11 haneli rakam).'
        
        # Teşhis alanının kontrolü
        if not teshis:
            errors['teshis'] = 'Lütfen teşhis bilgisini giriniz.'
            
        
        # Eğer hata varsa, formu yeniden render ediyoruz ve hata mesajlarını gösteriyoruz
        if errors:
            return render_template('index.html', errors=errors)

        # Veritabanı bağlantısı kuruyoruz
        conn = get_db_connection()

        try:
            doktor_id = session['user']['id']  # Giriş yapan doktorun ID'sini alıyoruz
            # Veritabanına hasta kaydediyoruz
            conn.execute(
                'INSERT INTO hastalar (ad, soyad, tckn, teshis, doktor_id) VALUES (?, ?, ?, ?, ?)',
                (name, surname, tckn, teshis, doktor_id)
            )
            conn.commit()  # Değişiklikleri kaydediyoruz
            session.pop('disease_result', None)
            conn.close()  # Bağlantıyı kapatıyoruz
            

            # Başarılı mesajı ekliyoruz
            flash('Hasta başarıyla kaydedildi!', 'success')
            return redirect(url_for('home'))  # Başarıyla kaydedildiğinde ana sayfaya yönlendirme
        except Exception as e:
            # Hata durumunda, hata mesajını göster
            conn.close()
            flash('Bir hata oluştu: ' + str(e), 'danger')
            return redirect(url_for('home'))  # Hata mesajı ile ana sayfaya dön



@app.route('/logout')
def logout():
    # Kullanıcıyı çıkış yaptır
    session.pop('user', None)  # Oturumdan 'user' bilgisini sil
    return redirect(url_for('login'))  # Login sayfasına yönlendir

@app.route('/index')
def index():
    if 'user' not in session:
        return redirect(url_for('login'))
    
    user = session['user']  # Bu satır, 'user' session'dan alındıktan sonra çalışmalı
    session.pop('disease_result', None)  # disease_result'ı temizle
    return render_template('index.html', user=user)  # 'user' verisini template'e geçir


@app.route('/patients', methods=['GET'])
def patients():
    if 'user' not in session:
        return redirect(url_for('login'))

    conn = get_db_connection()  # Veritabanı bağlantısı
    doktor_id = session['user']['id']  # Giriş yapan doktorun ID'sini alıyoruz

    # Sayfalama parametresi (varsayılan olarak 1. sayfa)
    page = request.args.get('page', 1, type=int)

    # Her sayfada gösterilecek hasta sayısı
    per_page = 10

    # Toplam hasta sayısını al
    total_patients = conn.execute('SELECT COUNT(*) FROM hastalar WHERE doktor_id = ?', (doktor_id,)).fetchone()[0]

    # Sayfa başına kaç hastanın geleceğini ve hangi hastaların alınacağını hesapla
    offset = (page - 1) * per_page

    # Sadece o doktora ait hastaları çekiyoruz
    patients_list = conn.execute(
        'SELECT * FROM hastalar WHERE doktor_id = ? LIMIT ? OFFSET ?',
        (doktor_id, per_page, offset)
    ).fetchall()

    conn.close()

    # Toplam sayfa sayısını hesapla
    total_pages = (total_patients + per_page - 1) // per_page  # Yuvarlama yukarı

    return render_template(
        'patients.html', 
        user=session.get('user'), 
        patients=patients_list, 
        page=page, 
        total_pages=total_pages
    )

# @app.route('/predict', methods=['GET', 'POST'])
# def predict():
#     return render_template('predict.html', user=session.get('user'))


@app.route('/patient_search', methods=['GET', 'POST'])
def patient_search():
    patient = None  # Başlangıçta hasta bilgisi yok
    if request.method == 'POST':
        tcno = request.form['tcno']
        
        # Kullanıcının (doktorun) oturum bilgilerini alıyoruz
        doktor_id = session.get('user', {}).get('id')  # Giriş yapan doktorun ID'sini alıyoruz
        
        if not doktor_id:
            flash("Lütfen giriş yapın.", "danger")
            return redirect(url_for('login'))  # Giriş yapılmamışsa login sayfasına yönlendir
        
        # Veritabanına bağlan
        conn = get_db_connection()
        
        # Girilen TC No'ya göre hastayı ve aynı zamanda doktor_id'yi kontrol ederek sorgulama yapıyoruz
        patient = conn.execute('''
            SELECT * FROM hastalar 
            WHERE tckn = ? AND doktor_id = ?
        ''', (tcno, doktor_id)).fetchone()
        conn.close()

        # Eğer hasta bulunmazsa, mesaj göstermek için flash
        if not patient:
            flash("Bu TC No ile kayıtlı hasta bulunamadı ya da başka bir doktora ait.", "danger")
    
    return render_template('patient_search.html', user=session.get('user'), patient=patient)


@app.route('/sil/<int:id>', methods=['POST'])
def sil(id):
    # Kullanıcı oturumu kontrol et
    if 'user' not in session:
        return redirect(url_for('login'))
    
    # Veritabanı bağlantısını oluştur
    conn = get_db_connection()

    try:
        # Kullanıcı (doktor) ID'sinin, silinecek hastanın doktoru ile eşleşip eşleşmediğini kontrol et
        doktor_id = session['user']['id']

        # Silinecek hastanın doktorunu kontrol et
        hastalar = conn.execute('SELECT * FROM hastalar WHERE id = ? AND doktor_id = ?', (id, doktor_id)).fetchone()

        if hastalar:
            # Hastayı sil
            conn.execute('DELETE FROM hastalar WHERE id = ?', (id,))
            conn.commit()
            flash('Hasta başarıyla silindi!', 'success')
        else:
            flash('Bu hastayı silemezsiniz. Doktorunuz değil.', 'danger')

        return redirect(url_for('home'))

    except Exception as e:
        # Hata durumunda, hata mesajını göster
        conn.close()
        flash('Bir hata oluştu: ' + str(e), 'danger')
        return redirect(url_for('home'))

@app.route('/edit_patient/<int:id>', methods=['GET', 'POST'])
def edit_patient(id):
    if 'user' not in session:
        return redirect(url_for('login'))

    # Veritabanına bağlan
    conn = get_db_connection()

    # Hastayı ID'ye göre al
    patient = conn.execute('SELECT * FROM hastalar WHERE id = ?', (id,)).fetchone()

    if not patient:
        flash('Hasta bulunamadı.', 'danger')
        return redirect(url_for('home'))

    # Formdan gelen verileri güncelleme işlemi
    if request.method == 'POST':
        name = request.form['name']
        surname = request.form['surname']
        tckn = request.form['tckn']
        teshis = request.form['teshis']

        # Veritabanı güncellemesi
        conn.execute('''
            UPDATE hastalar
            SET ad = ?, soyad = ?, tckn = ?, teshis = ?
            WHERE id = ?
        ''', (name, surname, tckn, teshis, id))
        conn.commit()
        conn.close()

        flash('Hasta bilgileri başarıyla güncellendi!', 'success')
        return redirect(url_for('home'))

    # Düzenleme formunu render et
    return render_template('edit_patients.html',user=session.get('user'), patient=patient)

@app.route('/predicts')
def predicts():
    return render_template('predict.html',user=session.get('user'))


@app.route('/settings', methods=['GET', 'POST'])
def settings():
    if request.method == 'POST':
        old_password = request.form['old_password']
        new_password = request.form['new_password']
        confirm_password = request.form['confirm_password']

        # Kullanıcının id'sini session'dan alıyoruz
        user_id = session['user']['id']
        
        # Veritabanına bağlan
        conn = get_db_connection()

        # E-posta adresi ile kullanıcıyı sorgulama (id'yi kullanarak daha güvenli)
        user = conn.execute('SELECT * FROM kullanicilar WHERE id = ?', (user_id,)).fetchone()

        # Eski şifrenin doğruluğunu kontrol et
        if user and user['parola'] == old_password:
            # Yeni şifre ile onay şifresinin eşleşip eşleşmediğini kontrol et
            if new_password != confirm_password:
                return render_template('settings.html', error="Yeni şifreler eşleşmiyor!")

            # Yeni şifreyi güncelle
            conn.execute('UPDATE kullanicilar SET parola = ? WHERE id = ?', (new_password, user_id))
            conn.commit()
            conn.close()  # Bağlantıyı kapat

            # Şifre değişikliğinden sonra ana sayfaya yönlendir
            return redirect(url_for('home'))

        else:
            conn.close()  # Bağlantıyı kapat
            return render_template('settings.html', error="Eski şifre yanlış!")

    return render_template('settings.html', user=session.get('user'))


if __name__ == '__main__':
    app.run(debug=True)
