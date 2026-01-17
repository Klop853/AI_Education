import streamlit as st
import os
import json
import smtplib
import zipfile
import io
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
from dotenv import load_dotenv
from langchain_groq import ChatGroq
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage

# --- CONFIGURACIÓN INICIAL ---
st.set_page_config(page_title="Práctica 3 - Entorno Seguro", page_icon="🛡️", layout="wide")

# Cargar API Key
api_key = st.secrets.get("GROQ_API_KEY") or os.getenv("GROQ_API_KEY")
if not api_key:
    st.error("⚠️ Falta la API Key. Configura los secrets.")
    st.stop()

# Inicializar modelo
llm = ChatGroq(groq_api_key=api_key, model_name="llama-3.3-70b-versatile", temperature=0.3)

# --- GESTIÓN DE ESTADO ---
if "step" not in st.session_state:
    st.session_state.step = 0  # 0: Login, 1: Examen, 2: Auditoría, 3: Veredicto
if "student_data" not in st.session_state:
    st.session_state.student_data = {"nombre": "", "apellidos": "", "matricula": ""}
if "chat_history" not in st.session_state:
    st.session_state.chat_history = [] 
if "exam_code" not in st.session_state:
    st.session_state.exam_code = ""    
if "audit_questions_json" not in st.session_state:
    st.session_state.audit_questions_json = [] 
if "audit_answers_dict" not in st.session_state:
    st.session_state.audit_answers_dict = {}
if "final_verdict" not in st.session_state:
    st.session_state.final_verdict = ""
if "email_status" not in st.session_state:
    st.session_state.email_status = None

# --- FUNCIONES AUXILIARES (EMAIL Y ZIP) ---

def crear_zip_en_memoria(chat_str, codigo_str, defensa_str, informe_str, alumno_nombre):
    """Crea un archivo ZIP en memoria con todos los documentos."""
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        # 1. Chat
        zf.writestr(f"1_chat_log_{alumno_nombre}.txt", chat_str)
        # 2. Código (asumimos .py por defecto, pero es texto)
        zf.writestr(f"2_codigo_examen_{alumno_nombre}.py", codigo_str)
        # 3. Defensa
        zf.writestr(f"3_defensa_auditoria_{alumno_nombre}.txt", defensa_str)
        # 4. Informe
        zf.writestr(f"4_informe_juez_{alumno_nombre}.md", informe_str)
    
    zip_buffer.seek(0)
    return zip_buffer

def enviar_paquete_completo(zip_buffer, alumno_data, informe_md):
    """Envía el ZIP por correo con el informe en el cuerpo."""
    destinatario = "jorgecuevas.cc@gmail.com"
    remitente = st.secrets.get("EMAIL_USER")
    password = st.secrets.get("EMAIL_PASSWORD")
    
    nombre_completo = f"{alumno_data['nombre']} {alumno_data['apellidos']}"
    matricula = alumno_data['matricula']

    if not remitente or not password:
        return False 

    try:
        msg = MIMEMultipart()
        msg['From'] = remitente
        msg['To'] = destinatario
        msg['Subject'] = f"ENTREGA EXAMEN: {nombre_completo} ({matricula})"

        cuerpo = f"""
        <html>
        <body>
            <h2>Entrega de Examen Finalizada</h2>
            <p><strong>Alumno:</strong> {nombre_completo}</p>
            <p><strong>Matrícula:</strong> {matricula}</p>
            <hr>
            <h3>Resumen del Veredicto:</h3>
            {informe_md.replace(chr(10), '<br>')}
            <hr>
            <p><em>Se adjunta archivo ZIP con toda la evidencia (Chat, Código, Respuestas).</em></p>
        </body>
        </html>
        """
        msg.attach(MIMEText(cuerpo, 'html'))

        # Adjuntar ZIP
        part = MIMEBase('application', "octet-stream")
        part.set_payload(zip_buffer.read())
        encoders.encode_base64(part)
        filename = f"Entrega_{matricula}_{alumno_data['apellidos']}.zip"
        part.add_header('Content-Disposition', f'attachment; filename="{filename}"')
        msg.attach(part)

        # Enviar
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(remitente, password)
        server.sendmail(remitente, destinatario, msg.as_string())
        server.quit()
        return True
    except Exception as e:
        print(f"Error enviando email: {e}")
        return False

# --- PROMPTS DEL SISTEMA ---
# (Mismos prompts que validamos antes)
prompt_tutor = """
<ROL>
Eres un asistente docente experto en multitud de temas.
Eres riguroso, pero amable y dispuesto a ayudar siempre y cuando se trate de incentivar el razonamiento y aprendizaje del alumno.
</ROL>
<CONTEXTO>
El alumno está en un examen. Puede usarte, pero tú no puedes resolverle el examen.
Tus respuestas influirán en el cuestionario de validación posterior.
</CONTEXTO>
<OBJETIVO>
Incentivarás el pensamiento. NO des código funcional completo.
Si el alumno pide código, responde con preguntas conceptuales o pseudocódigo abstracto.
Si explicas algo nuevo, INCLUYE PREGUNTAS AL FINAL que el alumno debería saber responder si ha entendido.
</OBJETIVO>
<REGLAS_INFRANQUEABLES>
1. NUNCA escribas código funcional ejecutable.
2. Usa el método socrático.
3. Si el alumno pega un error, pregúntale qué cree que falla, no se lo arregles.
</REGLAS_INFRANQUEABLES>
"""

prompt_auditor = """
<ROL>
Eres un Auditor Experto. Tu trabajo es verificar la autoría intelectual del código.
</ROL>
<TAREA>
Analiza el código y genera EXACTAMENTE 5 preguntas de verificación profunda numeradas.
Las preguntas deben ir al detalle: por qué usó tal variable, qué pasa si cambia X por Y, etc.
</TAREA>
<FORMATO_OBLIGATORIO>
Debes responder ÚNICAMENTE con un array JSON de strings válidos.
Ejemplo exacto:
["Pregunta 1...", "Pregunta 2...", "Pregunta 3...", "Pregunta 4...", "Pregunta 5..."]
</FORMATO_OBLIGATORIO>
"""

prompt_juez = """
<ROL>
Eres el juez final. Corregirás las respuestas del alumno y emitirás un informe de integridad.
</ROL>
<INPUTS>
1. [CHAT]: Historial de dudas.
2. [EXAMEN]: Código entregado.
3. [DEFENSA]: Preguntas del auditor y respuestas del alumno.
</INPUTS>
<ALGORITMO>
- CASO A (Fraude): Código perfecto + Chat vacío/irrelevante + Defensa pobre. -> SUSPENSO.
- CASO B (Aceptable): Dudas razonables + Defensa sólida. -> APROBADO.
- CASO C (Excelencia): Chat técnico + Defensa brillante. -> SOBRESALIENTE.
<SALIDA>
Genera un informe Markdown con:
1. **Nivel de Confianza de Autoría**: (0-100%).
2. **Evidencia Clave**.
3. **Análisis de la Defensa**: Detallado por pregunta.
4. **Nota Sugerida**: (0-10) con bonus si aprendió durante el chat.
5. **Conclusión Final**: Párrafo de cierre.
</SALIDA>
"""

# --- INTERFAZ GRÁFICA ---

st.title("🛡️ Entorno de Examen Asistido por IA")

# --- FASE 0: IDENTIFICACIÓN ---
if st.session_state.step == 0:
    st.header("Identificación del Alumno")
    st.info("Por favor, introduce tus datos para comenzar el examen.")
    
    with st.form("login_form"):
        col1, col2 = st.columns(2)
        nombre = col1.text_input("Nombre")
        apellidos = col2.text_input("Apellidos")
        matricula = st.text_input("Número de Matrícula / ID")
        
        submitted = st.form_submit_button("Comenzar Examen")
        
        if submitted:
            if nombre and apellidos and matricula:
                st.session_state.student_data = {
                    "nombre": nombre,
                    "apellidos": apellidos,
                    "matricula": matricula
                }
                st.session_state.step = 1
                st.rerun()
            else:
                st.error("Por favor, rellena todos los campos.")

# --- BARRA LATERAL (Solo visible tras login) ---
if st.session_state.step > 0:
    st.sidebar.title(f"Alumno: {st.session_state.student_data['nombre']}")
    st.sidebar.caption(f"ID: {st.session_state.student_data['matricula']}")
    st.sidebar.divider()
    st.sidebar.markdown(f"{'🟢' if st.session_state.step == 1 else '⚪'} 1. Desarrollo y Consultas")
    st.sidebar.markdown(f"{'🟢' if st.session_state.step == 2 else '⚪'} 2. Entrega y Validación")
    st.sidebar.markdown(f"{'🟢' if st.session_state.step == 3 else '⚪'} 3. Veredicto")

# --- FASE 1: CHAT ---
if st.session_state.step == 1:
    st.header("Fase 1: Examen en curso")
    st.info("La IA no te dará código, pero te guiará. Debes entender lo que escribes, pues se te preguntará tras la entrega.")
    
    for msg in st.session_state.chat_history:
        role = "user" if isinstance(msg, HumanMessage) else "assistant"
        with st.chat_message(role):
            st.write(msg.content)

    user_input = st.chat_input("Duda conceptual...")
    if user_input:
        st.session_state.chat_history.append(HumanMessage(content=user_input))
        with st.chat_message("user"):
            st.write(user_input)
        
        with st.chat_message("assistant"):
            with st.spinner("Pensando..."):
                messages = [SystemMessage(content=prompt_tutor)] + st.session_state.chat_history
                response = llm.invoke(messages)
                st.write(response.content)
                st.session_state.chat_history.append(AIMessage(content=response.content))

    st.divider()
    uploaded_file = st.file_uploader("Sube tu examen (.py o .ipynb)", type=["py", "ipynb", "txt"])
    if uploaded_file and st.button("Entregar y Validar"):
        st.session_state.exam_code = uploaded_file.read().decode("utf-8")
        st.session_state.step = 2
        st.rerun()

# --- FASE 2: AUDITORÍA ---
elif st.session_state.step == 2:
    st.header("Fase 2: Validación de Conocimientos")
    
    if not st.session_state.audit_questions_json:
        with st.spinner("Analizando código y generando preguntas específicas..."):
            audit_msg = [
                SystemMessage(content=prompt_auditor),
                HumanMessage(content=f"Código del alumno:\n{st.session_state.exam_code}")
            ]
            response = llm.invoke(audit_msg)
            try:
                questions_list = json.loads(response.content)
                if isinstance(questions_list, list):
                    st.session_state.audit_questions_json = questions_list
                else:
                    st.session_state.audit_questions_json = ["Error formato. Responde abajo."]
            except:
                st.session_state.audit_questions_json = ["Error de lectura de preguntas. Comenta tu código brevemente."]

    if st.session_state.audit_questions_json:
        with st.form("audit_form"):
            st.success("Responde a estas 5 preguntas sobre tu código:")
            
            answers = {}
            for i, question in enumerate(st.session_state.audit_questions_json):
                st.markdown(f"**{question}**")
                answers[f"q{i}"] = st.text_area(f"Respuesta {i+1}", key=f"ans_{i}")
            
            submit_btn = st.form_submit_button("Enviar respuestas y Terminar Examen")

            if submit_btn:
                st.session_state.audit_answers_dict = answers
                
                with st.spinner("Generando paquete de entrega y enviando al profesor..."):
                    # 1. Preparar Strings para el ZIP
                    chat_str = "\n".join([f"{'User' if isinstance(m, HumanMessage) else 'AI'}: {m.content}\n---" for m in st.session_state.chat_history])
                    
                    defensa_str = ""
                    for i, q in enumerate(st.session_state.audit_questions_json):
                        defensa_str += f"PREGUNTA {i+1}: {q}\nRESPUESTA: {answers[f'q{i}']}\n\n{'='*20}\n\n"

                    # 2. Generar Veredicto
                    evidence = f"HISTORIAL CHAT:\n{chat_str}\n\nCÓDIGO:\n{st.session_state.exam_code}\n\nDEFENSA:\n{defensa_str}"
                    juez_msg = [SystemMessage(content=prompt_juez), HumanMessage(content=evidence)]
                    veredicto = llm.invoke(juez_msg)
                    st.session_state.final_verdict = veredicto.content
                    
                    # 3. Crear ZIP en memoria
                    zip_buffer = crear_zip_en_memoria(
                        chat_str, 
                        st.session_state.exam_code, 
                        defensa_str, 
                        veredicto.content, 
                        st.session_state.student_data['apellidos']
                    )

                    # 4. Enviar Email con ZIP
                    email_exito = enviar_paquete_completo(zip_buffer, st.session_state.student_data, veredicto.content)
                    st.session_state.email_status = email_exito
                    
                    st.session_state.step = 3
                    st.rerun()

# --- FASE 3: FIN ---
elif st.session_state.step == 3:
    st.header(f"Examen Finalizado: {st.session_state.student_data['nombre']}")
    
    if st.session_state.email_status:
        st.success("✅ Entrega Exitosa. Se ha enviado un archivo ZIP con tu examen, chat y validación al profesor.")
    else:
        st.warning("⚠️ Modo Simulación: El archivo se ha generado internamente pero no se envió el email (Faltan credenciales).")
    
    st.info("Este informe será enviado automáticamente al profesor. Has terminado el examen.")
    st.markdown("### Resumen del Veredicto:")
    st.markdown("---")
    st.markdown(st.session_state.final_verdict)
    
    if st.button("Finalizar Sesión (Reiniciar)"):
        st.session_state.clear()
        st.rerun()
