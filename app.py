from flask import Flask, request, render_template, send_from_directory, redirect, url_for
import os
from werkzeug.utils import secure_filename
from pdf2image import convert_from_path
import pickle
from paddleocr import PaddleOCR
import time 
import numpy as np
from PIL import Image


app = Flask(__name__)

# 设置上传文件的路径
UPLOAD_FOLDER = 'uploads'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['ALLOWED_EXTENSIONS'] = {'pdf'}

# 检查文件扩展名
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']


#  介绍页面
@app.route('/')
def index():
    return render_template('index.html')

#  扫描审查页
@app.route('/scanprecheck')
def scanprecheck():
    if os.path.exists(os.path.join(app.config['UPLOAD_FOLDER'], 'last_pdf.pkl')):
        with open(os.path.join(app.config['UPLOAD_FOLDER'], 'last_pdf.pkl'), 'rb') as f:
            pdf_info = pickle.load(f)
        if pdf_info['success']:
            pdf_name = list(pdf_info.keys())[0]
            image_paths = pdf_info[pdf_name]
            return render_template('scanprecheck.html', pdf_name = pdf_name , current_page=0, succ=f'{time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())}已成功读取上次PDF', total_pages=len(image_paths))

        else:
            return render_template('scanprecheck.html', error='读取失败')

    return render_template('scanprecheck.html')

# 快速扫描审查
@app.route('/quickscan', methods=['POST'])
def quickscan():
    if 'file' not in request.files:
        return '没有文件部分'
    file = request.files['file']
    if file.filename == '':
        return '没有选择文件'
    if file and allowed_file(file.filename):
        try:
            filename = secure_filename(file.filename)
            pdf_name = filename.split('.')[0] # pdf文件名
            pdf_sp = os.path.join(app.config['UPLOAD_FOLDER'], pdf_name) # pdf文件路径
            if not os.path.exists(pdf_sp):
                os.makedirs(pdf_sp)
            file.save(os.path.join(pdf_sp, filename))
            file_path = os.path.join(pdf_sp, filename)

            # 转换PDF为图像
            images = convert_from_path(file_path, poppler_path='poppler-24.08.0/Library/bin')
            image_paths = []
            for i, image in enumerate(images):

                image_path = os.path.join('static', 'images', pdf_name)
                if not os.path.exists(image_path):
                    os.makedirs(image_path)
                image_path = os.path.join(image_path, f'page_{i}.png')
                for_html_path = os.path.join('images', pdf_name, f'page_{i}.png')
                
                image.save(os.path.join(image_path), 'PNG')
                image_paths.append(for_html_path)

            # 将读取成功的pdf_name、image_paths保存到文件中 使用pkl
            with open(os.path.join(app.config['UPLOAD_FOLDER'], 'last_pdf.pkl'), 'wb') as f:
                pickle.dump({pdf_name:image_paths,"success": True}, f)
            print('读取成功')
            
            # return redirect(url_for('scanprecheck'))
            return render_template('scanprecheck.html', pdf_name = pdf_name , current_page=0, succ=f'{time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())}PDF转Image成功', total_pages=len(image_paths))

        except Exception as e:
            with open(os.path.join(app.config['UPLOAD_FOLDER'], 'last_pdf.pkl'), 'wb') as f:
                pickle.dump({pdf_name:None, "success": False}, f)
            print(f'读取失败{e}')
            return redirect(url_for('scanprecheck'))

    return '文件格式不支持'

# 上一页、下一页、跳转指定页面等按键，可以绑定键盘快捷键
@app.route('/navigate', methods=['POST'])
def navigate():
    if os.path.exists(os.path.join(app.config['UPLOAD_FOLDER'], 'last_pdf.pkl')):
        with open(os.path.join(app.config['UPLOAD_FOLDER'], 'last_pdf.pkl'), 'rb') as f:
            pdf_info = pickle.load(f)
        if pdf_info['success']:
            pdf_name = list(pdf_info.keys())[0]
            image_paths = pdf_info[pdf_name]

            action = request.form.get('action')
            try:
                current_page = int(request.form.get('current_page'))
            except:
                current_page = 0
            total_pages = int(request.form.get('total_pages', 0))
            
            if action == 'next':
                current_page = min(current_page + 1, total_pages - 1)
            elif action == 'prev':
                current_page = max(current_page - 1, 0)
            elif action == 'goto':
                target_page = int(request.form.get('target_page', 0))
                current_page = min(max(target_page, 0), total_pages - 1)   

            return render_template('scanprecheck.html', pdf_name = pdf_name , current_page=current_page, total_pages=len(image_paths), succ='读取成功')
        
        else:
            return render_template('scanprecheck.html', error='读取失败')    

# {pdf_name:image_paths,
#  "success": True
#  }
@app.route('/finish_scan', methods=['POST'])
def finish_scan():
    if os.path.exists(os.path.join(app.config['UPLOAD_FOLDER'], 'last_pdf.pkl')):
        with open(os.path.join(app.config['UPLOAD_FOLDER'], 'last_pdf.pkl'), 'rb') as f:
            pdf_info = pickle.load(f)
        if pdf_info['success']:
            pdf_name = list(pdf_info.keys())[0]
            image_paths = pdf_info[pdf_name]
            action = request.form.get('action')
            if action == 'finish':
                pdf_info['precheck'] = True
                with open(os.path.join(app.config['UPLOAD_FOLDER'], 'last_pdf.pkl'), 'wb') as f:
                    pickle.dump(pdf_info, f)
                return render_template('scanprecheck.html', pdf_name = pdf_name , current_page=0, total_pages=len(image_paths), check='初审成功，请前往程序初次分类页面，进行分类')
            else:
                return render_template('scanprecheck.html', pdf_name = pdf_name , current_page=0, total_pages=len(image_paths),  chekcerror='初审失败')

        else:
            return render_template('scanprecheck.html', chekcerror='初审失败')

@app.route('/preclassifyandcheck') 
def preclassifyandcheck(): # 初步分类与分类审查
    if os.path.exists(os.path.join(app.config['UPLOAD_FOLDER'], 'last_pdf.pkl')):
        with open(os.path.join(app.config['UPLOAD_FOLDER'], 'last_pdf.pkl'), 'rb') as f:
            pdf_info = pickle.load(f)    
        try:
            if pdf_info['precheck']:
                pdf_name = list(pdf_info.keys())[0]
                try:
                    if pdf_info['classified_for_each_part']:
                        return render_template('preclassifyandcheck.html',pdf_name = pdf_name, classify=f'已读取上次程序初分类结果')
                except:
                    return render_template('preclassifyandcheck.html',pdf_name = pdf_name)
        except:
            return render_template('precheckerror.html')
    return render_template('precheckerror.html')


@app.route('/preclassify', methods=['POST'])  
def preclassify(): # 初次分类、核心功能、生成pdf
    if os.path.exists(os.path.join(app.config['UPLOAD_FOLDER'], 'last_pdf.pkl')):
        with open(os.path.join(app.config['UPLOAD_FOLDER'], 'last_pdf.pkl'), 'rb') as f:
            pdf_info = pickle.load(f)    
        if pdf_info['precheck']:
            pdf_name = list(pdf_info.keys())[0]
            action = request.form.get('action')
            classified_for_each_part = {
                '苹果': [],
                '香蕉': [],
                '橘子': [],
                '其他': [],
                '未分类': [],
                '空白': []
            }
            if action == 'classify':  # 程序初次分类核心 
                pdf_info['preclassify'] = True
                classified_pdf = process_pdf(pdf_info[pdf_name])
                for key, value in classified_pdf.items():
                    if value == '苹果':
                        classified_for_each_part['苹果'].append(key)
                    elif value == '香蕉':
                        classified_for_each_part['香蕉'].append(key)
                    elif value == '橘子':
                        classified_for_each_part['橘子'].append(key)
                    elif value == '其他':
                        classified_for_each_part['其他'].append(key)
                    else:
                        classified_for_each_part['未分类'].append(key)
                pdf_info['classified_for_each_part'] = classified_for_each_part
                with open(os.path.join(app.config['UPLOAD_FOLDER'], 'last_pdf.pkl'), 'wb') as f:
                    pickle.dump(pdf_info, f)

                return render_template('preclassifyandcheck.html',
                                       pdf_name = pdf_name, 
                                       classify=f'{time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())}初次分类成功')
            
            elif action == 'genpdf':  # 生成pdf 
                try:
                    if not os.path.exists(os.path.join(app.config['UPLOAD_FOLDER'], pdf_name, 'result')):
                        os.makedirs(os.path.join(app.config['UPLOAD_FOLDER'], pdf_name, 'result'))
                    for k,v in pdf_info['classified_for_each_part'].items():
                        images = [Image.open(os.path.join('static',img)).convert("RGB") for img in v]
                        if images:
                            images[0].save(os.path.join(app.config['UPLOAD_FOLDER'], pdf_name, 'result', f'{k}.pdf'), save_all=True, append_images=images[1:])                    
                    return render_template('preclassifyandcheck.html',pdf_name = pdf_name, genpdf='pdf生成成功') 
                except:
                    return render_template('preclassifyandcheck.html',pdf_name = pdf_name, genpdferror='pdf生成失败')               
            else:
                return render_template('preclassifyandcheck.html',pdf_name = pdf_name, classifyerror='分类失败')

@app.route('/progresscheckfail', methods=['GET', 'POST'])  
def progresscheckfail(): # 未分类文书 快速分类
    if request.method == 'POST':
        if os.path.exists(os.path.join(app.config['UPLOAD_FOLDER'], 'last_pdf.pkl')):
            with open(os.path.join(app.config['UPLOAD_FOLDER'], 'last_pdf.pkl'), 'rb') as f:
                pdf_info = pickle.load(f)
                image_paths = pdf_info['classified_for_each_part']['未分类']
            if image_paths:
                pdf_name = list(pdf_info.keys())[0]
                path2num = [int(i.split('_')[-1].split('.')[0]) for i in image_paths]
                action = request.form.get('action')
                try:
                    current_page = int(request.form.get('current_page'))
                except:
                    current_page = 0
                total_pages = int(request.form.get('total_pages', 0))
                
                if action == 'next':
                    current_page = min(current_page + 1, total_pages - 1)
                elif action == 'prev':
                    current_page = max(current_page - 1, 0)
                elif action == 'goto':
                    target_page = int(request.form.get('target_page', 0))
                    current_page = min(max(target_page, 0), total_pages - 1)   
                elif action == 'psb':
                    pdf_info['classified_for_each_part']['苹果'].append(image_paths[current_page])
                    image_paths.remove(image_paths[current_page])
                    with open(os.path.join(app.config['UPLOAD_FOLDER'], 'last_pdf.pkl'), 'wb') as f:
                        pickle.dump(pdf_info, f)
                    return render_template('classifiyandcheck.html', pdf_name = pdf_name , current_page=current_page+1, path2num=path2num, total_pages=len(image_paths), succ='读取成功', curr_class= '未分类')
                elif action == 'nsa':
                    pdf_info['classified_for_each_part']['香蕉'].append(image_paths[current_page])
                    image_paths.remove(image_paths[current_page])
                    with open(os.path.join(app.config['UPLOAD_FOLDER'], 'last_pdf.pkl'), 'wb') as f:
                        pickle.dump(pdf_info, f)
                    return render_template('classifiyandcheck.html', pdf_name = pdf_name , current_page=current_page+1, path2num=path2num, total_pages=len(image_paths), succ='读取成功', curr_class= '未分类')
                elif action == 'ccdi':
                    pdf_info['classified_for_each_part']['橘子'].append(image_paths[current_page])
                    image_paths.remove(image_paths[current_page])
                    with open(os.path.join(app.config['UPLOAD_FOLDER'], 'last_pdf.pkl'), 'wb') as f:
                        pickle.dump(pdf_info, f)
                    return render_template('classifiyandcheck.html', pdf_name = pdf_name , current_page=current_page+1, path2num=path2num, total_pages=len(image_paths), succ='读取成功', curr_class= '未分类')
                elif action == 'other':
                    pdf_info['classified_for_each_part']['其他'].append(image_paths[current_page])
                    image_paths.remove(image_paths[current_page])
                    with open(os.path.join(app.config['UPLOAD_FOLDER'], 'last_pdf.pkl'), 'wb') as f:
                        pickle.dump(pdf_info, f)
                    return render_template('classifiyandcheck.html', pdf_name = pdf_name , current_page=current_page+1, path2num=path2num, total_pages=len(image_paths), succ='读取成功', curr_class= '未分类')
                elif action == 'blank':
                    # pdf_info['classified_for_each_part']['苹果'].append(image_paths[current_page])
                    # pdf_info['classified_for_each_part']['未分类'].remove(image_paths[current_page])
                    # with open(os.path.join(app.config['UPLOAD_FOLDER'], 'last_pdf.pkl'), 'wb') as f:
                    #     pickle.dump(pdf_info, f)
                    print('blank')
                    return render_template('classifiyandcheck.html', pdf_name = pdf_name , current_page=current_page+1, path2num=path2num, total_pages=len(image_paths), succ='读取成功', curr_class= '未分类')
                return render_template('classifiyandcheck.html', pdf_name = pdf_name , current_page=current_page, path2num=path2num, total_pages=len(image_paths), succ='读取成功', curr_class= '未分类')
            else:
                return render_template('classifiyandcheck.html', error='读取失败')            
    else: # GET
        if os.path.exists(os.path.join(app.config['UPLOAD_FOLDER'], 'last_pdf.pkl')):
            with open(os.path.join(app.config['UPLOAD_FOLDER'], 'last_pdf.pkl'), 'rb') as f:
                pdf_info = pickle.load(f)    
            pdf_name = list(pdf_info.keys())[0]
            image_paths = pdf_info['classified_for_each_part']['未分类']
            path2num = [int(i.split('_')[-1].split('.')[0]) for i in image_paths]            
            if image_paths:
                return render_template('classifiyandcheck.html', unclassifiy='存在未分类文书', pdf_name = pdf_name, current_page=0, path2num=path2num, total_pages=len(image_paths), curr_class= '未分类')
        
        else:
            return render_template('classifiyandcheck.html', error='不存在未分类文书')

@app.route('/psbcheck', methods=['GET', 'POST']) 
def psbcheck(): # 苹果 快速审阅与分类
    if request.method == 'POST':
        if os.path.exists(os.path.join(app.config['UPLOAD_FOLDER'], 'last_pdf.pkl')):
            with open(os.path.join(app.config['UPLOAD_FOLDER'], 'last_pdf.pkl'), 'rb') as f:
                pdf_info = pickle.load(f)
            image_paths = pdf_info['classified_for_each_part']['苹果']
            if image_paths:
                pdf_name = list(pdf_info.keys())[0]
                path2num = [int(i.split('_')[-1].split('.')[0]) for i in image_paths]
                action = request.form.get('action')
                try:
                    current_page = int(request.form.get('current_page'))
                except:
                    current_page = 0
                total_pages = int(request.form.get('total_pages', 0))
                
                if action == 'next':
                    current_page = min(current_page + 1, total_pages - 1)
                elif action == 'prev':
                    current_page = max(current_page - 1, 0)
                elif action == 'goto':
                    target_page = int(request.form.get('target_page', 0))
                    current_page = min(max(target_page, 0), total_pages - 1)   
                elif action == 'psb':
                    print('psb')
                    return render_template('classifiyandcheck.html', pdf_name = pdf_name , current_page=current_page+1, path2num=path2num, total_pages=len(image_paths), succ='读取成功', curr_class= '苹果')
                elif action == 'nsa':
                    pdf_info['classified_for_each_part']['香蕉'].append(image_paths[current_page])
                    image_paths.remove(image_paths[current_page])
                    with open(os.path.join(app.config['UPLOAD_FOLDER'], 'last_pdf.pkl'), 'wb') as f:
                        pickle.dump(pdf_info, f)
                    return render_template('classifiyandcheck.html', pdf_name = pdf_name , current_page=current_page+1, path2num=path2num, total_pages=len(image_paths), succ='读取成功', curr_class= '苹果')
                elif action == 'ccdi':
                    pdf_info['classified_for_each_part']['橘子'].append(image_paths[current_page])
                    image_paths.remove(image_paths[current_page])
                    with open(os.path.join(app.config['UPLOAD_FOLDER'], 'last_pdf.pkl'), 'wb') as f:
                        pickle.dump(pdf_info, f)
                    return render_template('classifiyandcheck.html', pdf_name = pdf_name , current_page=current_page+1, path2num=path2num, total_pages=len(image_paths), succ='读取成功', curr_class= '苹果')
                elif action == 'other':
                    pdf_info['classified_for_each_part']['其他'].append(image_paths[current_page])
                    image_paths.remove(image_paths[current_page])
                    with open(os.path.join(app.config['UPLOAD_FOLDER'], 'last_pdf.pkl'), 'wb') as f:
                        pickle.dump(pdf_info, f)
                    return render_template('classifiyandcheck.html', pdf_name = pdf_name , current_page=current_page+1, path2num=path2num, total_pages=len(image_paths), succ='读取成功', curr_class= '苹果')
                elif action == 'blank':
                    pdf_info['classified_for_each_part']['未分类'].append(image_paths[current_page])
                    image_paths.remove(image_paths[current_page])
                    with open(os.path.join(app.config['UPLOAD_FOLDER'], 'last_pdf.pkl'), 'wb') as f:
                        pickle.dump(pdf_info, f)
                    return render_template('classifiyandcheck.html', pdf_name = pdf_name , current_page=current_page+1, path2num=path2num, total_pages=len(image_paths), succ='读取成功', curr_class= '苹果')
                return render_template('classifiyandcheck.html', pdf_name = pdf_name , current_page=current_page, path2num=path2num, total_pages=len(image_paths), succ='读取成功', curr_class= '苹果')

            else:
                return render_template('classifiyandcheck.html', error='读取失败')            
    else: # GET
        if os.path.exists(os.path.join(app.config['UPLOAD_FOLDER'], 'last_pdf.pkl')):
            with open(os.path.join(app.config['UPLOAD_FOLDER'], 'last_pdf.pkl'), 'rb') as f:
                pdf_info = pickle.load(f)    
            pdf_name = list(pdf_info.keys())[0]
            image_paths = pdf_info['classified_for_each_part']['苹果']
            path2num = [int(i.split('_')[-1].split('.')[0]) for i in image_paths]            
            if image_paths:
                return render_template('classifiyandcheck.html', unclassifiy='请审核', pdf_name = pdf_name, current_page=0, path2num=path2num, total_pages=len(image_paths), curr_class= '苹果')
        
        else:
            return render_template('classifiyandcheck.html', error='不存在未分类文书')
            
    return render_template('psbcheck.html')

@app.route('/nsacheck', methods=['GET', 'POST']) 
def nsacheck(): # 香蕉 快速审阅与分类
    if request.method == 'POST':
        if os.path.exists(os.path.join(app.config['UPLOAD_FOLDER'], 'last_pdf.pkl')):
            with open(os.path.join(app.config['UPLOAD_FOLDER'], 'last_pdf.pkl'), 'rb') as f:
                pdf_info = pickle.load(f)
                image_paths = pdf_info['classified_for_each_part']['香蕉']
            if image_paths:
                pdf_name = list(pdf_info.keys())[0]
                path2num = [int(i.split('_')[-1].split('.')[0]) for i in image_paths]
                action = request.form.get('action')
                try:
                    current_page = int(request.form.get('current_page'))
                except:
                    current_page = 0
                total_pages = int(request.form.get('total_pages', 0))
                
                if action == 'next':
                    current_page = min(current_page + 1, total_pages - 1)
                elif action == 'prev':
                    current_page = max(current_page - 1, 0)
                elif action == 'goto':
                    target_page = int(request.form.get('target_page', 0))
                    current_page = min(max(target_page, 0), total_pages - 1)   
                elif action == 'psb':
                    pdf_info['classified_for_each_part']['苹果'].append(image_paths[current_page])
                    image_paths.remove(image_paths[current_page])
                    with open(os.path.join(app.config['UPLOAD_FOLDER'], 'last_pdf.pkl'), 'wb') as f:
                        pickle.dump(pdf_info, f)
                    return render_template('classifiyandcheck.html', pdf_name = pdf_name , current_page=current_page+1, path2num=path2num, total_pages=len(image_paths), succ='读取成功', curr_class= '香蕉')
                elif action == 'nsa':
                    print('nsa')
                    return render_template('classifiyandcheck.html', pdf_name = pdf_name , current_page=current_page+1, path2num=path2num, total_pages=len(image_paths), succ='读取成功', curr_class= '香蕉')
                elif action == 'ccdi':
                    pdf_info['classified_for_each_part']['橘子'].append(image_paths[current_page])
                    image_paths.remove(image_paths[current_page])
                    with open(os.path.join(app.config['UPLOAD_FOLDER'], 'last_pdf.pkl'), 'wb') as f:
                        pickle.dump(pdf_info, f)
                    return render_template('classifiyandcheck.html', pdf_name = pdf_name , current_page=current_page+1, path2num=path2num, total_pages=len(image_paths), succ='读取成功', curr_class= '香蕉')
                elif action == 'other':
                    pdf_info['classified_for_each_part']['其他'].append(image_paths[current_page])
                    image_paths.remove(image_paths[current_page])
                    with open(os.path.join(app.config['UPLOAD_FOLDER'], 'last_pdf.pkl'), 'wb') as f:
                        pickle.dump(pdf_info, f)
                    return render_template('classifiyandcheck.html', pdf_name = pdf_name , current_page=current_page+1, path2num=path2num, total_pages=len(image_paths), succ='读取成功', curr_class= '香蕉')
                elif action == 'blank':
                    pdf_info['classified_for_each_part']['未分类'].append(image_paths[current_page])
                    image_paths.remove(image_paths[current_page])
                    with open(os.path.join(app.config['UPLOAD_FOLDER'], 'last_pdf.pkl'), 'wb') as f:
                        pickle.dump(pdf_info, f)
                    print('blank')
                    return render_template('classifiyandcheck.html', pdf_name = pdf_name , current_page=current_page+1, path2num=path2num, total_pages=len(image_paths), succ='读取成功', curr_class= '香蕉')
                return render_template('classifiyandcheck.html', pdf_name = pdf_name , current_page=current_page, path2num=path2num, total_pages=len(image_paths), succ='读取成功', curr_class= '香蕉')
            
            else:
                return render_template('classifiyandcheck.html', error='读取失败')            
    else: # GET
        if os.path.exists(os.path.join(app.config['UPLOAD_FOLDER'], 'last_pdf.pkl')):
            with open(os.path.join(app.config['UPLOAD_FOLDER'], 'last_pdf.pkl'), 'rb') as f:
                pdf_info = pickle.load(f)    
            pdf_name = list(pdf_info.keys())[0]
            image_paths = pdf_info['classified_for_each_part']['香蕉']
            path2num = [int(i.split('_')[-1].split('.')[0]) for i in image_paths]            
            if image_paths:

                return render_template('classifiyandcheck.html', unclassifiy='请审核', pdf_name = pdf_name, current_page=0, path2num=path2num, total_pages=len(image_paths), curr_class= '香蕉')
        
        else:
            return render_template('classifiyandcheck.html', error='不存在未分类文书')    
    return render_template('nsacheck.html')

@app.route('/ccdicheck' ,methods=['GET', 'POST'])
def ccdicheck(): # 橘子 快速审阅与分类
    if request.method == 'POST':
        if os.path.exists(os.path.join(app.config['UPLOAD_FOLDER'], 'last_pdf.pkl')):
            with open(os.path.join(app.config['UPLOAD_FOLDER'], 'last_pdf.pkl'), 'rb') as f:
                pdf_info = pickle.load(f)
            image_paths = pdf_info['classified_for_each_part']['橘子']
            if image_paths:
                pdf_name = list(pdf_info.keys())[0]
                path2num = [int(i.split('_')[-1].split('.')[0]) for i in image_paths]
                action = request.form.get('action')
                try:
                    current_page = int(request.form.get('current_page'))
                except:
                    current_page = 0
                total_pages = int(request.form.get('total_pages', 0))
                
                if action == 'next':
                    current_page = min(current_page + 1, total_pages - 1)
                elif action == 'prev':
                    current_page = max(current_page - 1, 0)
                elif action == 'goto':
                    target_page = int(request.form.get('target_page', 0))
                    current_page = min(max(target_page, 0), total_pages - 1)   
                elif action == 'psb':
                    pdf_info['classified_for_each_part']['苹果'].append(image_paths[current_page])
                    image_paths.remove(image_paths[current_page])
                    with open(os.path.join(app.config['UPLOAD_FOLDER'], 'last_pdf.pkl'), 'wb') as f:
                        pickle.dump(pdf_info, f)
                    return render_template('classifiyandcheck.html', pdf_name = pdf_name , current_page=current_page+1, path2num=path2num, total_pages=len(image_paths), succ='读取成功', curr_class= '橘子')
                elif action == 'nsa':
                    pdf_info['classified_for_each_part']['香蕉'].append(image_paths[current_page])
                    image_paths.remove(image_paths[current_page])
                    with open(os.path.join(app.config['UPLOAD_FOLDER'], 'last_pdf.pkl'), 'wb') as f:
                        pickle.dump(pdf_info, f)
                    return render_template('classifiyandcheck.html', pdf_name = pdf_name , current_page=current_page+1, path2num=path2num, total_pages=len(image_paths), succ='读取成功', curr_class= '橘子')
                elif action == 'ccdi':
                    pdf_info['classified_for_each_part']['橘子'].append(image_paths[current_page])
                    image_paths.remove(image_paths[current_page])
                    with open(os.path.join(app.config['UPLOAD_FOLDER'], 'last_pdf.pkl'), 'wb') as f:
                        pickle.dump(pdf_info, f)
                    return render_template('classifiyandcheck.html', pdf_name = pdf_name , current_page=current_page+1, path2num=path2num, total_pages=len(image_paths), succ='读取成功', curr_class= '橘子')
                elif action == 'other':
                    pdf_info['classified_for_each_part']['其他'].append(image_paths[current_page])
                    image_paths.remove(image_paths[current_page])
                    with open(os.path.join(app.config['UPLOAD_FOLDER'], 'last_pdf.pkl'), 'wb') as f:
                        pickle.dump(pdf_info, f)
                    return render_template('classifiyandcheck.html', pdf_name = pdf_name , current_page=current_page+1, path2num=path2num, total_pages=len(image_paths), succ='读取成功', curr_class= '橘子')
                elif action == 'blank':
                    pdf_info['classified_for_each_part']['未分类'].append(image_paths[current_page])
                    image_paths.remove(image_paths[current_page])
                    with open(os.path.join(app.config['UPLOAD_FOLDER'], 'last_pdf.pkl'), 'wb') as f:
                        pickle.dump(pdf_info, f)
                    return render_template('classifiyandcheck.html', pdf_name = pdf_name , current_page=current_page+1, path2num=path2num, total_pages=len(image_paths), succ='读取成功', curr_class= '橘子')
                return render_template('classifiyandcheck.html', pdf_name = pdf_name , current_page=current_page, path2num=path2num, total_pages=len(image_paths), succ='读取成功', curr_class= '橘子')
            else:
                return render_template('classifiyandcheck.html', error='读取失败')            
    else: # GET
        if os.path.exists(os.path.join(app.config['UPLOAD_FOLDER'], 'last_pdf.pkl')):
            with open(os.path.join(app.config['UPLOAD_FOLDER'], 'last_pdf.pkl'), 'rb') as f:
                pdf_info = pickle.load(f)    
            pdf_name = list(pdf_info.keys())[0]
            image_paths = pdf_info['classified_for_each_part']['橘子']
            path2num = [int(i.split('_')[-1].split('.')[0]) for i in image_paths]            
            if image_paths:
                return render_template('classifiyandcheck.html', unclassifiy='请审核', pdf_name = pdf_name, current_page=0, path2num=path2num, total_pages=len(image_paths), curr_class= '橘子')
        
        else:
            return render_template('classifiyandcheck.html', error='不存在未分类文书')
    return render_template('cdicheck.html')

@app.route('/othercheck' ,methods=['GET', 'POST'])
def othercheck(): # 其他 快速审阅与分类
    if request.method == 'POST':
        if os.path.exists(os.path.join(app.config['UPLOAD_FOLDER'], 'last_pdf.pkl')):
            with open(os.path.join(app.config['UPLOAD_FOLDER'], 'last_pdf.pkl'), 'rb') as f:
                pdf_info = pickle.load(f)

            image_paths = pdf_info['classified_for_each_part']['其他']                
            if image_paths:
                pdf_name = list(pdf_info.keys())[0]
                path2num = [int(i.split('_')[-1].split('.')[0]) for i in image_paths]
                action = request.form.get('action')
                try:
                    current_page = int(request.form.get('current_page'))
                except:
                    current_page = 0
                total_pages = int(request.form.get('total_pages', 0))
                
                if action == 'next':
                    current_page = min(current_page + 1, total_pages - 1)
                elif action == 'prev':
                    current_page = max(current_page - 1, 0)
                elif action == 'goto':
                    target_page = int(request.form.get('target_page', 0))
                    current_page = min(max(target_page, 0), total_pages - 1)   


                elif action == 'psb':
                    pdf_info['classified_for_each_part']['苹果'].append(image_paths[current_page])
                    image_paths.remove(image_paths[current_page])
                    with open(os.path.join(app.config['UPLOAD_FOLDER'], 'last_pdf.pkl'), 'wb') as f:
                        pickle.dump(pdf_info, f)
                    return render_template('classifiyandcheck.html', pdf_name = pdf_name , current_page=current_page+1, path2num=path2num, total_pages=len(image_paths), succ='读取成功', curr_class= '其他')
                elif action == 'nsa':
                    pdf_info['classified_for_each_part']['香蕉'].append(image_paths[current_page])
                    image_paths.remove(image_paths[current_page])
                    with open(os.path.join(app.config['UPLOAD_FOLDER'], 'last_pdf.pkl'), 'wb') as f:
                        pickle.dump(pdf_info, f)
                    return render_template('classifiyandcheck.html', pdf_name = pdf_name , current_page=current_page+1, path2num=path2num, total_pages=len(image_paths), succ='读取成功', curr_class= '其他')
                elif action == 'ccdi':
                    pdf_info['classified_for_each_part']['橘子'].append(image_paths[current_page])
                    image_paths.remove(image_paths[current_page])
                    with open(os.path.join(app.config['UPLOAD_FOLDER'], 'last_pdf.pkl'), 'wb') as f:
                        pickle.dump(pdf_info, f)
                    return render_template('classifiyandcheck.html', pdf_name = pdf_name , current_page=current_page+1, path2num=path2num, total_pages=len(image_paths), succ='读取成功', curr_class= '其他')
                elif action == 'other':
                    pdf_info['classified_for_each_part']['其他'].append(image_paths[current_page])
                    image_paths.remove(image_paths[current_page])
                    with open(os.path.join(app.config['UPLOAD_FOLDER'], 'last_pdf.pkl'), 'wb') as f:
                        pickle.dump(pdf_info, f)
                    return render_template('classifiyandcheck.html', pdf_name = pdf_name , current_page=current_page+1, path2num=path2num, total_pages=len(image_paths), succ='读取成功', curr_class= '其他')
                elif action == 'blank':
                    pdf_info['classified_for_each_part']['未分类'].append(image_paths[current_page])
                    image_paths.remove(image_paths[current_page])
                    with open(os.path.join(app.config['UPLOAD_FOLDER'], 'last_pdf.pkl'), 'wb') as f:
                        pickle.dump(pdf_info, f)
                    print('blank')
                    return render_template('classifiyandcheck.html', pdf_name = pdf_name , current_page=current_page+1, path2num=path2num, total_pages=len(image_paths), succ='读取成功', curr_class= '其他')
                return render_template('classifiyandcheck.html', pdf_name = pdf_name , current_page=current_page, path2num=path2num, total_pages=len(image_paths), succ='读取成功', curr_class= '其他')
            else:
                return render_template('classifiyandcheck.html', error='读取失败')            
    else: # GET
        if os.path.exists(os.path.join(app.config['UPLOAD_FOLDER'], 'last_pdf.pkl')):
            with open(os.path.join(app.config['UPLOAD_FOLDER'], 'last_pdf.pkl'), 'rb') as f:
                pdf_info = pickle.load(f)    
            pdf_name = list(pdf_info.keys())[0]
            image_paths = pdf_info['classified_for_each_part']['其他']
            path2num = [int(i.split('_')[-1].split('.')[0]) for i in image_paths]            
            if image_paths:
                return render_template('classifiyandcheck.html', unclassifiy='请审核', pdf_name = pdf_name, current_page=0, path2num=path2num, total_pages=len(image_paths), curr_class= '其他')
        
        else:
            return render_template('classifiyandcheck.html', error='不存在未分类文书')
    return render_template('othercheck.html')

def process_pdf(image_paths):  # 初分类核心程序
    ocr = PaddleOCR(use_angle_cls=True, lang='ch')  # need to run only once to download and load model into memory
    psb_classify_words = {'苹果': 0.9}  # 苹果
    nsa_classify_words = {'香蕉': 1.0}  # 香蕉
    ccdi_classify_words = {'橘子': 1.0}  # 橘子
    other_classify_words = {'其他': 0.9          
                            }  # 其他
    classified_dict = {i:0 for i in image_paths}
    # 使用OCR提取文本 page为图像
    for num, page in enumerate(image_paths):

        ocr_start = time.time()
        result = ocr.ocr(os.path.join('static',page), cls=True)
        print(f'第{num + 1}ocr time: ', time.time() - ocr_start)

        for idx in range(len(result)):
            try:
                res = result[idx]
                line_weight = 0
                for line in res:
                    text = line[1][0]
                    for category, words in [('其他', other_classify_words),
                                            ('香蕉', nsa_classify_words),
                                            ('橘子', ccdi_classify_words),
                                            ('苹果', psb_classify_words),
                                            ]:
                        for key, weight in words.items():
                            if key in text:
                                if weight > line_weight:
                                    line_weight = weight
                                    classified_dict[page]= category
                                print(f'{category}: {text} 分类词权重: {weight}')

                                
            except:
                print(f'error 第{num + 1}页面，未识别到内容')
    return classified_dict

if __name__ == '__main__':
    if not os.path.exists(UPLOAD_FOLDER):
        os.makedirs(UPLOAD_FOLDER)
    app.run(debug=True)
