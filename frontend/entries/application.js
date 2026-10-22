/*!
 * Axios (MIT)
 * # Copyright (c) 2014-present Matt Zabriskie & Collaborators
 *
 * Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:
 *
 * The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.
 *
 * THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
 */
import axios from 'axios';

const form = document.getElementById('application-form');
const fields = document.getElementById('application-fields');
const submit = document.getElementById('submit-application');
const feedback = document.getElementById('submission-status');
const search = document.getElementById('search-address');
const searchArea = document.getElementById('address-search');
const embed = document.getElementById('postcode-embed');
const addressFeedback = document.getElementById('address-feedback');
const reload = document.getElementById('reload-education');
let accepting = false;
let busy = false;
let completed = false;
let conflicted = false;
let uncertain = false;
// 응답 유실 후에도 최초 payload와 ID를 함께 유지해야 서버의 중복 제출 보호가 적용된다.
let snapshot = null;
let csrfToken = form.elements.csrfmiddlewaretoken.value;
let postcodePromise = null;

function closeSearch(restoreFocus = true) {
  searchArea.hidden = true;
  search.setAttribute('aria-expanded', 'false');
  if (restoreFocus && !fields.disabled) {
    search.focus();
  }
}

/** 결과 미확인 중에는 편집을 막되 같은 제출의 결과 확인은 허용한다. */
function updateControls() {
  fields.disabled = busy || uncertain || conflicted || completed || !accepting;
  submit.disabled = busy || conflicted || completed || (!accepting && !snapshot);
  submit.textContent = busy ? '접수 결과를 확인하고 있습니다…' :
    (uncertain ? '같은 신청 다시 확인하기' : '상담 신청 접수하기');
  form.setAttribute('aria-busy', String(busy));
  if (fields.disabled) {
    closeSearch(false);
  }
}

function clearErrors() {
  form.querySelectorAll('[data-field-error]').forEach((node) => {
    node.textContent = '';
  });
  fields.querySelectorAll('[aria-invalid]').forEach((node) => {
    node.removeAttribute('aria-invalid');
  });
}

/** 공개 API의 최신 접수 상태를 확인하기 전까지 신규 제출을 차단한다. */
async function loadEducation() {
  reload.disabled = true;
  try {
    const {data} = await axios.get(form.dataset.educationUrl, {timeout: 15000});
    document.getElementById('selected-title').textContent = data.title;
    document.getElementById('selected-summary').textContent = data.summary;
    document.getElementById('selected-note').textContent = data.operation_note;
    document.getElementById('selected-operation').textContent =
      data.operation_type === 'courseware' ? '코스웨어' : '코치 출강';
    const image = document.getElementById('selected-image');
    if (data.image_url) {
      image.src = data.image_url;
      image.alt = data.image_alt;
      image.classList.remove('hidden');
    }
    accepting = data.is_accepting_inquiries === true;
    document.getElementById('education-status').textContent = accepting ?
      '상담 접수 가능' : '현재 신규 상담 접수가 중단되었습니다.';
    reload.classList.add('hidden');
  } catch {
    accepting = false;
    document.getElementById('education-status').textContent =
      '교육 정보를 불러오지 못했습니다. 잠시 후 다시 시도해 주세요.';
    reload.classList.remove('hidden');
  } finally {
    reload.disabled = false;
    updateControls();
  }
}

/** 결과 미확인 요청의 ID·입력은 보존하고 다음 재시도에 쓸 CSRF token만 갱신한다. */
async function refreshCsrf() {
  await axios.get('/', {timeout: 15000});
  const cookie = document.cookie.split('; ').find((value) => value.startsWith('csrftoken='));
  if (cookie) {
    csrfToken = decodeURIComponent(cookie.slice('csrftoken='.length));
  }
}

/** DRF 필드 오류를 연결된 안내에 표시하고 첫 오류 입력으로 포커스를 이동한다. */
function showFieldErrors(data) {
  let first = null;
  Object.entries(data).forEach(([name, messages]) => {
    const input = fields.elements.namedItem(name);
    const error = document.getElementById(`${name}-error`);
    if (input && error && Array.isArray(messages)) {
      error.textContent = messages.join(' ');
      input.setAttribute('aria-invalid', 'true');
      first ??= input;
    }
  });
  first?.focus();
}

// 확정된 미저장 오류만 수정을 허용하고 결과 유실·409에서는 새 ID를 자동 생성하지 않는다.
form.addEventListener('submit', async (event) => {
  event.preventDefault();
  if (busy || completed || conflicted || (!snapshot && !accepting)) {
    return;
  }
  if (!snapshot) {
    if (!form.reportValidity()) {
      return;
    }
    snapshot = Object.fromEntries(new FormData(form));
    delete snapshot.csrfmiddlewaretoken;
    snapshot.education_slug = form.dataset.slug;
    snapshot.request_id = crypto.randomUUID();
  }
  const wasUncertain = uncertain;
  clearErrors();
  busy = true;
  feedback.textContent = '신청을 전송하고 접수 결과를 확인하고 있습니다.';
  updateControls();
  let fieldErrors = null;
  try {
    const {data} = await axios.post(form.dataset.submitUrl, snapshot, {
      timeout: 15000,
      headers: {'X-CSRFToken': csrfToken},
    });
    if (data?.status !== 'received' || data.request_id !== snapshot.request_id) {
      throw new Error('invalid-receipt');
    }
    completed = true;
    uncertain = false;
    feedback.textContent = `접수되었습니다. 신청 상태: 접수 · 접수 식별자: ${data.request_id}`;
    feedback.focus();
  } catch (error) {
    const response = error.response;
    const status = response?.status;
    const data = response?.data;
    if (status === 409) {
      conflicted = true;
      feedback.textContent = '제출 식별자가 다른 내용에 사용되었습니다. 중복 접수를 막기 위해 자동 재전송을 중단했습니다.';
    } else if ((status === 400 || status === 404) && data && typeof data === 'object') {
      uncertain = false;
      snapshot = null;
      feedback.textContent = status === 404 ? '교육 정보를 찾을 수 없습니다. 교육 소개를 확인해 주세요.' :
        (data.education_slug?.[0] || '입력 내용을 확인한 뒤 다시 신청해 주세요.');
      fieldErrors = status === 400 ? data : null;
    } else if (status === 403) {
      uncertain = wasUncertain;
      if (!wasUncertain) {
        snapshot = null;
      }
      try {
        await refreshCsrf();
        feedback.textContent = wasUncertain ?
          '보안 확인을 갱신했습니다. 이전 접수 결과는 아직 미확인입니다. 같은 신청 다시 확인하기를 눌러 주세요.' :
          '보안 확인을 갱신했습니다. 내용을 확인하고 다시 접수해 주세요.';
      } catch {
        feedback.textContent = '보안 확인을 갱신하지 못했습니다. 잠시 후 같은 페이지에서 다시 시도해 주세요.';
      }
    } else {
      uncertain = true;
      feedback.textContent = '접수 여부를 아직 확인하지 못했습니다. 입력을 변경하거나 새로고침하지 말고 같은 신청 다시 확인하기를 눌러 주세요.';
    }
  } finally {
    busy = false;
    updateControls();
    if (fieldErrors) {
      showFieldErrors(fieldErrors);
    }
  }
});

/** 주소 검색을 요청할 때만 공식 SDK를 로딩하고 실패하면 다음 시도를 허용한다. */
function loadPostcode() {
  if (window.kakao?.Postcode) {
    return Promise.resolve();
  }
  if (!postcodePromise) {
    postcodePromise = new Promise((resolve, reject) => {
      const script = document.createElement('script');
      const timer = setTimeout(() => {
        script.remove();
        reject(new Error('postcode-timeout'));
      }, 10000);
      script.src = 'https://t1.kakaocdn.net/mapjsapi/bundle/postcode/prod/postcode.v2.js';
      script.async = true;
      script.onload = () => {
        clearTimeout(timer);
        if (window.kakao?.Postcode) {
          resolve();
        } else {
          reject(new Error('postcode-unavailable'));
        }
      };
      script.onerror = () => {
        clearTimeout(timer);
        script.remove();
        reject(new Error('postcode-load-failed'));
      };
      document.head.append(script);
    }).catch((error) => {
      postcodePromise = null;
      throw error;
    });
  }
  return postcodePromise;
}

search.addEventListener('click', async () => {
  let loadFailed = false;
  search.disabled = true;
  addressFeedback.textContent = '주소 검색을 불러오고 있습니다.';
  try {
    await loadPostcode();
    if (fields.disabled) {
      return;
    }
    embed.replaceChildren();
    searchArea.hidden = false;
    search.setAttribute('aria-expanded', 'true');
    new window.kakao.Postcode({
      width: '100%',
      height: '100%',
      onresize: ({height}) => { embed.style.height = `${height}px`; },
      oncomplete: (data) => {
        // 검색을 기다리는 동안 제출이 시작되거나 취소됐다면 보존 중인 입력을 바꾸지 않는다.
        if (fields.disabled || searchArea.hidden) {
          return;
        }
        form.elements.postal_code.value = data.zonecode;
        form.elements.address.value = data.userSelectedType === 'R' ? data.roadAddress : data.jibunAddress;
        closeSearch(false);
        form.elements.address_detail.focus();
        addressFeedback.textContent = '주소를 입력했습니다. 상세주소를 확인해 주세요.';
      },
    }).embed(embed);
    addressFeedback.textContent = '검색어를 입력해 주소를 선택해 주세요.';
  } catch {
    loadFailed = true;
    closeSearch(false);
    addressFeedback.textContent = '주소 검색을 사용할 수 없습니다. 우편번호와 주소를 직접 입력하거나 다시 시도해 주세요.';
  } finally {
    search.disabled = false;
    if (loadFailed && !fields.disabled) {
      search.focus();
    }
  }
});
document.getElementById('cancel-address').addEventListener('click', () => {
  closeSearch();
  addressFeedback.textContent = '검색을 취소했습니다. 입력한 주소는 유지됩니다.';
});
reload.addEventListener('click', loadEducation);
loadEducation();
