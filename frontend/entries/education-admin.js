document.addEventListener('DOMContentLoaded', () => {
  for (const editor of document.querySelectorAll('[data-curriculum-editor]')) {
    const button = editor.querySelector('[data-add-lesson]');
    const total = editor.querySelector('input[name$="-TOTAL_FORMS"]');
    const template = editor.querySelector('[data-curriculum-template]');
    const rows = editor.querySelector('[data-curriculum-rows]');
    button.disabled = false;
    button.addEventListener('click', () => {
      const content = template.content.cloneNode(true);
      // 같은 인덱스로 입력 이름과 레이블 연결을 함께 바꿔 formset 제출 구조를 유지한다.
      for (const element of content.querySelectorAll('[name], [id], [for]')) {
        for (const attribute of ['name', 'id', 'for']) {
          if (element.hasAttribute(attribute)) {
            element.setAttribute(attribute,
              element.getAttribute(attribute).replaceAll('__prefix__', total.value));
          }
        }
      }
      const firstInput = content.querySelector('input');
      rows.append(content);
      total.value = String(Number(total.value) + 1);
      firstInput.focus();
    });
  }
});
