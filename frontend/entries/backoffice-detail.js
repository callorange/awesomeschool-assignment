/*!
 * Axios (MIT)
 * Copyright (c) 2014-present Matt Zabriskie & Collaborators
 * Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:
 * The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.
 * THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
 */
/**
 * @fileoverview 상세의 이메일 표시만 갱신하며 신청·상담 폼과 저장 동작에는 관여하지 않는다.
 * 인증 오류·네트워크 실패는 기존 표시를 유지하고 자동 이동·재전송하지 않는다.
 */
import axios from 'axios';

const refresh = document.getElementById('refresh-email');
const status = document.getElementById('email-status');
const feedback = document.getElementById('email-feedback');
const login = document.getElementById('email-login');

if (refresh) {
  refresh.disabled = false;
  feedback.textContent = '작성 중인 신청·상담은 유지하고 이메일 상태만 확인합니다.';
  refresh.addEventListener('click', async () => {
    refresh.disabled = true;
    status.setAttribute('aria-busy', 'true');
    login.hidden = true;
    feedback.textContent = '이메일 처리 상태를 확인하고 있습니다.';
    try {
      const response = await axios.get(refresh.dataset.url, {timeout: 15000});
      // 같은 사이트의 권한 검사·escaping을 거친 전용 HTML 조각만 이메일 영역에 넣는다.
      status.innerHTML = response.data;
      feedback.textContent = '이메일 처리 상태를 새로 확인했습니다.';
    } catch (error) {
      const code = error.response?.status;
      if (code === 401) {
        feedback.textContent = '로그인이 만료되었습니다. 입력은 유지됩니다. 별도 탭에서 다시 로그인해 주세요.';
        login.hidden = false;
      } else if (code === 403) {
        feedback.textContent = '이메일 처리 상태를 조회할 권한이 없습니다. 기존 표시와 입력은 유지됩니다.';
      } else {
        feedback.textContent = '상태 갱신에 실패했습니다. 기존 표시는 최신 상태가 아닐 수 있습니다. 다시 시도해 주세요.';
      }
    } finally {
      refresh.disabled = false;
      status.removeAttribute('aria-busy');
      refresh.focus();
    }
  });
}
