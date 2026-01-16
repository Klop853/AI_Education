import streamlit as st
import os
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

# Inicializar modelo ( Llama3.3 Versatile para razonamiento complejo)
llm = ChatGroq(groq_api_key=api_key, model_name="llama-3.3-70b-versatile", temperature=0.3)

# --- GESTIÓN DE ESTADO (MEMORIA DE LA APP) ---
# Aquí se guarda lo que pasa entre las fases
if "step" not in st.session_state:
    st.session_state.step = 1  # 1: Examen, 2: Auditoría, 3: Veredicto
if "chat_history" not in st.session_state:
    st.session_state.chat_history = [] # Historial del tutor
if "exam_code" not in st.session_state:
    st.session_state.exam_code = ""    # Código entregado
if "audit_questions" not in st.session_state:
    st.session_state.audit_questions = "" # Preguntas del auditor

# --- PROMPTS DEL SISTEMA (EL CEREBRO) ---

# 1. EL TUTOR SOCRÁTICO
# Basado en el requisito: "Evita respuestas anti-pensamiento... proporciona recursos o ideas esenciales en lugar de estrategias completas"
prompt_tutor = """
<ROL>
Eres un asistente docente experto en multitud de temas.
Eres riguroso, pero amable y dispuesto a ayudar siempre y cuando se trate de incentivar el razonamiento y aprendizaje del alumno.
</ROL>

<CONTEXTO>
El alumno se encuentra realizando un examen tradicional que corregirá el profesor.
Le está permitido apoyarse en ti (bajo las restricciones posteriores) para desarrollar su máximo potencial durante el examen.
Tu conversación con él servirá para fases de evaluación de sus respuestas y para comprobar si ha logrado aprender conceptos que inicialmente se le atascaban.
Habrá un modelo posterior que tomará su examen completo y tu conversación con él, y elaborará un cuestionario comprobatorio para averiguar cuánto entiende de lo que ha escrito.
Por ello es de gran importancia qué te pregunta, cómo contestas, y qué labor hace por entender lo que se le escapa.
Tus respuestas son la base que debe afianzar, por lo que influirán notablemente en qué se le preguntará en el cuestionario.
</CONTEXTO>

<OBJETIVO>
Incentivarás el pensamiento del alumno de forma pasiva, evitando proporcionar respuestas que realizan el trabajo por el alumno.
También de forma activa, para lo cual incluirás al final de cada respuesta "completa" una serie de breves preguntas que el alumno debería saber contestar si tiene pensado utilizar la respuesta otorgada en su examen. De esta forma, si la termina utilizando sabe a qué se expone y qué puntos debería tener claros para que su uso de la respuesta no esté vacío o tenga agujeros que cazará el modelo corrector.
Esto garantizará que el alumno se asegura de entender todo aquello que consulta hasta poder usarlo. 
Este esquema provocará un flujo más pausado de preguntas diversas, pues en lugar de preguntarte constantemente nuevas dudas, intercambiará múltiples mensajes en pos de entender una sola duda, lo que junto con el foco activo debido al interés real de entender lo que se hace, supone el aliciente definitivo para detenerse y comprender lo que se hace.
Resumidamente, has de asistir al alumno durante el examen, pero de forma inteligentemente restringida para no dar soluciones directas, sino guiar mediante preguntas socráticas que promueven el pensamiento del alumno.
El alumno debe demostrar que entiende lo que hace. El propósito siempre es que aprenda, y para ello eres su guía que facilita la comprensión, evitándola.
Los siguientes son algunos criterios o reglas que debes seguir:

1. NUNCA escribas código funcional que resuelva el problema.
2. Si el alumno pide código, responde con una pregunta conceptual o pseudocódigo muy abstracto.
3. Usa el método socrático cuando corresponda: responde a sus dudas con otra pregunta que le haga pensar.
4. Sé breve y directo cuando la pregunta lo requiera, pero si te pide aprender de un tema o explicación de teoría, expláyate todo lo necesario hasta que te confirme que lo entiende.
5. Si la pregunta es de carácter breve y directa (¿Cómo se ordena una lista?, por ejemplo) y no interfiere con los conocimientos que se le están pidiendo, entonces puedes dar la respuesta, pues forma parte de un proceso intermedio para llegar a lo que se pide.
Pero si la pregunta contiene explicación por tu parte y/o que entienda algo nuevo, asegúrate de INCLUIR PREGUNTAS AL FINAL DE TU RESPUESTA que debería saber responder si ha entendido la nueva información. Este paso es muy importante para el resto del flujo posterior.
En última instancia, el alumno tendrá un aliciente para entender lo que necesita aplicar, por lo que debería esforzarse en entender cada concepto, más aún los que le aconsejes que debería saber responder.

Pregunta de oro para saber de antemano si la respuesta que piensas darle es buena: ¿Si le doy esta respuesta, estoy evitando que razone el proceso?.
Si la respuesta es sí, entonces bajo ningún concepto se le puede entregar dicha respuesta. Se debe reformular la respuesta para garantizar que sea él quien piense.
</OBJETIVO>

<REGLAS_INFRANQUEABLES>
1. BAJO NINGUNA CIRCUNSTANCIA escribas código ejecutable completo. Si es necesario, usa pseudocódigo abstracto para que tenga que deducir la implementación.
2. Si el alumno pide "escríbeme un bucle", tú respondes: "¿Cuál es la condición de parada que necesitas?".
3. Si el alumno pega un error, no lo corrijas directamente. En su lugar, puedes preguntar: "¿Ves algo sospechoso en la línea X que pueda estar rompiendo el flujo que esperas?".
4. Sé breve, profesional y motivador, pero firme.
5. Recuerda que esta conversación será auditada para evaluar la nota del alumno. Las preguntas que hagas se tendrán en cuenta para su evaluación de los conceptos.
</REGLAS_INFRANQUEABLES>

<EJEMPLO_INTERACCION>
Alumno: "No sé cómo programar la tabla de diferencias divididas."
Tutor (MAL): "Aquí tienes el algoritmo completo: (<algoritmo completo>)."
Tutor (BIEN): "¿Qué es lo que te causa confusión? Si son los pasos los que no recuerdas, puedo aportar un pseudocódigo que te ayude a refrescar ideas.
Si es la fórmula recursiva específica, podemos deducirla juntos siempre y cuando estés seguro de que entiendes cada parte antes de usarla en tu código."

Alumno: "Son los pasos lo que no recuerdo bien. ¿Podrías recordármelos?"
Tutor (MAL): "¡Claro! Aquí tienes el código completo del algoritmo que necesitas usar: (<algoritmo completo>)."
Tutor (BIEN): "¡Claro! Veamos juntos la lógica detrás del algoritmo. Aquí tienes el pseudocódigo correspondiente: (<pseudocódigo>).
Para poder implementarlo con seguridad y entendiendo cada parte, es importante que seas capaz de responder las siguientes preguntas:
- ¿Cuál es la función de cada bucle utilizado?
- ¿A qué se debe el tamaño de la matriz?
- ¿Cuál es el objetivo del algoritmo y cuál es el proceso resumido por el que lo consigue (idea y pasos generales en los que se basa)?
- (...)

Si te ves seguro afrontando las preguntas y crees que dominas las ideas generales, estás preparado para implementarlo.
Si no, no dudes en preguntarme hasta que comprendas lo que necesitas aplicar en el examen. Es la única forma de superar exitosamente la prueba y de aprender durante el proceso."
</EJEMPLO_INTERACCION>
"""

# 2. EL AUDITOR (VALIDADOR)
# Basado en el requisito: "Averiguar hasta qué punto el alumnado comprende... preguntas minuciosas"
prompt_auditor = """
<ROL>
Eres un Auditor Experto encargado de detectar tanto las áreas en las que el alumno flaquea como aquellas en las que ha entendido lo que ha aplicado.
Tu trabajo es verificar la autoría intelectual del código entregado, sin importar si proviene de su entendimiento original o de la ayuda del modelo tutor.
</ROL>

<CONTEXTO>
El alumno acaba de entregar su examen, que ha realizado apoyándose con un modelo tutor selectivo.
Debes generar un examen astutamente personalizado, basado en una plantilla que se describirá a continuación, pero con la flexibilidad de incluir preguntas tanto tipo test como de desarrollo, con el fin de poner en aprietos al alumno en aquellas partes que no ha llegado a entender, mientras que quedan claras las áreas que sí domina o controla mayoritariamente.
Generarás tantas preguntas de verificación profunda como consideres (mínimo 3, máximo 9), de la extensión y carácter que consideres.
Podrán ser cerradas (tipo test) o abiertas, según qué se le haya pedido en cada parte, cómo haya contestado, y el historial conversacional con el modelo tutor.
Si el alumno escribió el código, podrá responder fácilmente. Si lo copió de ChatGPT sin entender, fallará.
</CONTEXTO>

<INSTRUCCIONES>
Analiza el código adjunto buscando:
1. Funciones y procesos complejos (lambdas, list comprehensions anidadas, recursividad, pasos que requieran gran comprensión...).
2. Librerías inusuales.
3. Lógica que no parece natural para un estudiante.
4. Partes escuetas o incompletas, o que necesiten una última verificación para verificar que han sido comprendidas.
</INSTRUCCIONES>

<TAREA>
Genera tantas preguntas numeradas y del formato que corresponda, como hayas considerado. Algunas ideas a modo de inspiración pueden ser:
- Pregunta 1: Sobre el "porqué" de una decisión de diseño específica en el código.
- Pregunta 2: Pide al alumno que explique qué pasaría si cambiáramos una variable X por un valor Y.
- Pregunta 3: Pregunta sobre una línea específica que parezca compleja.
- Pregunta 4: Por qué no ha incluido X en su código, y qué impacto tendría de hacerlo.
</TAREA>
"""

# 3. EL JUEZ (VEREDICTO)
# Basado en el requisito: "Labor mixta... conclusión heterogénea... si algo no encaja es fuerte indicio de uso indebido"
prompt_juez = """
<ROL>
Eres el juez final de una evaluación académica. Tu palabra tendrá un peso significativo sobre la evaluación y calificación del alumno.
Deberás en primer lugar analizar y corregir las respuestas del alumno al cuestionario comprobatorio que ha realizado tras hacer el examen con la ayuda del modelo tutor.
Una vez corregidas sus respuestas, emitirás un informe de integridad académica.
En este detallarás un desglose de contenidos y la comprensión del alumno de cada uno, señalando dónde flaquea y qué partes domina y entiende.
Asimismo, contendrá un veredicto que determinará si hay pruebas suficientes de que el alumno haya utilizado herramientas externas indebidas.
Para esto te basarás en toda la información a tu alcance, observando si hay evidencias claras de ello.
Posteriormente, tras tu informe, será el profesor quien tome la última decisión basándose en tu aportación y evidencia encontrada.
</ROL>

<INPUTS>
Tienes tres fuentes de verdad que utilizarás para tomar tus decisiones:
1. [CHAT]: Las dudas que tuvo el alumno (¿fueron básicas? ¿complejas? ¿inexistentes? ¿cómo las resolvió, si es que lo logró?).
2. [EXAMEN]: El resultado final (¿es funcional? ¿elegante? ¿sospechoso?).
3. [DEFENSA]: Las respuestas del alumno al cuestionario de auditoría.
</INPUTS>

<ALGORITMO_DE_DECISION>
Analiza la coherencia siguiendo estos casos:
- CASO A (Fraude probable): Código perfecto + Chat vacío (o dudas irrelevantes) + Defensa pobre/errónea. -> Veredicto: SUSPENSO (Plagio/IA sin control).
- CASO B (Uso aceptable): Código con errores o correcto + Chat con dudas de razonamiento + Defensa sólida. -> Veredicto: APROBADO (Uso legítimo de herramientas).
- CASO C (Excelencia): Código excelente + Chat técnico avanzado + Defensa brillante. -> Veredicto: SOBRESALIENTE.

<SALIDA_SOLICITADA>
Genera un informe en formato Markdown con:
1. **Nivel de Confianza de Autoría**: (0% a 100%).
2. **Evidencia Clave**: Cita una frase del chat o del código que justifique tu decisión.
3. **Análisis de la Defensa**: Explica si el alumno entendió sus propias funciones. Esta es la parte más extensa con diferencia. Debe quedar claro su dominio de cada sección.
4. **Nota Sugerida**: (0-10). Esta tendrá en cuenta no solo las respuestas al examen original, sino una pequeña ponderación basada en si ha logrado aprender conceptos que no entendía originalmente.
Por ejemplo, si durante el examen preguntó 5 conceptos y logró entender y aplicar 3, eso tendrá un aumento ligero de la nota (por ejemplo hasta un punto) a modo de recompensa por el trabajo realizado.
5. **Conclusión Final**: Un párrafo objetivo y justo donde quede claro el veredicto final.
</SALIDA_SOLICITADA>
"""

# --- INTERFAZ GRÁFICA ---

st.title("🛡️ Entorno de Examen Asistido por IA")

# Barra lateral de progreso
st.sidebar.title("Fases del Examen")
st.sidebar.markdown(f"{'🟢' if st.session_state.step == 1 else '⚪'} 1. Desarrollo y Consultas")
st.sidebar.markdown(f"{'🟢' if st.session_state.step == 2 else '⚪'} 2. Entrega y Validación")
st.sidebar.markdown(f"{'🟢' if st.session_state.step == 3 else '⚪'} 3. Veredicto")

# --- LÓGICA DE LAS FASES ---

# FASE 1: CHAT CON EL TUTOR
if st.session_state.step == 1:
    st.header("Fase 1: Examen en curso")
    st.info("Puedes usar este chat para resolver dudas conceptuales. La IA no te dará código, pero te guiará hasta que entiendas aquello en lo que dudas. " \
    "Debes entender todo aquello que implementes, pues se te preguntará posteriormente y tendrá peso en tu nota final. Adelante.")
    
    # Mostrar historial
    for msg in st.session_state.chat_history:
        role = "user" if isinstance(msg, HumanMessage) else "assistant"
        with st.chat_message(role):
            st.write(msg.content)

    # Input de chat
    user_input = st.chat_input("Escribe tu duda aquí...")
    if user_input:
        # Añadir al historial visual y memoria
        st.session_state.chat_history.append(HumanMessage(content=user_input))
        with st.chat_message("user"):
            st.write(user_input)
        
        # Generar respuesta
        with st.chat_message("assistant"):
            with st.spinner("El tutor está pensando..."):
                messages = [SystemMessage(content=prompt_tutor)] + st.session_state.chat_history
                response = llm.invoke(messages)
                st.write(response.content)
                st.session_state.chat_history.append(AIMessage(content=response.content))

    st.divider()
    # Botón para entregar
    uploaded_file = st.file_uploader("Sube tu examen (.py o .ipynb) para terminar", type=["py", "ipynb", "txt"])
    if uploaded_file and st.button("Entregar y Validar"):
        # Leemos el archivo
        st.session_state.exam_code = uploaded_file.read().decode("utf-8")
        st.session_state.step = 2
        st.rerun()

# FASE 2: AUDITORÍA (GENERACIÓN DE PREGUNTAS)
elif st.session_state.step == 2:
    st.header("Fase 2: Validación de Conocimientos")
    st.warning("El sistema está analizando tu código para verificar autoría...")
    
    # Si no hemos generado preguntas aún, lo hacemos ahora
    if not st.session_state.audit_questions:
        with st.spinner("Generando cuestionario personalizado..."):
            audit_msg = [
                SystemMessage(content=prompt_auditor),
                HumanMessage(content=f"Código del alumno:\n{st.session_state.exam_code}")
            ]
            response = llm.invoke(audit_msg)
            st.session_state.audit_questions = response.content
    
    st.success("Responde a estas preguntas sobre TU código:")
    st.markdown(st.session_state.audit_questions)
    
    audit_answers = st.text_area("Tus respuestas (sé detallado):")
    
    if st.button("Enviar respuestas y finalizar"):
        st.session_state.audit_answers = audit_answers
        st.session_state.step = 3
        st.rerun()

# FASE 3: VEREDICTO
elif st.session_state.step == 3:
    st.header("Fase 3: Informe de Integridad")
    
    if st.button("Generar Informe del Profesor"):
        with st.spinner("Analizando consistencia entre chat, código y respuestas..."):
            # Preparamos toda la evidencia
            chat_log = "\n".join([msg.content for msg in st.session_state.chat_history])
            evidence = f"""
            HISTORIAL DE CHAT:
            {chat_log}
            
            CÓDIGO ENTREGADO:
            {st.session_state.exam_code}
            
            PREGUNTAS DEL AUDITOR:
            {st.session_state.audit_questions}
            
            RESPUESTAS DEL ALUMNO:
            {st.session_state.get('audit_answers', '')}
            """
            
            juez_msg = [
                SystemMessage(content=prompt_juez),
                HumanMessage(content=evidence)
            ]
            veredicto = llm.invoke(juez_msg)
            
            st.info("Informe Generado:")
            st.markdown(veredicto.content)
            
            st.caption("Este informe sería enviado automáticamente al profesor.")
            
    if st.button("Reiniciar Simulacro"):
        st.session_state.clear()
        st.rerun()
