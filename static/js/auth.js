function login() {
	const id = $('#loginId').val();
	const pw = $('#loginPw').val();
	let $errorBox = $('#error-msg');

	$errorBox.addClass('hidden');

	if (id == '' || pw == '') {
		$errorBox.text('아이디와 비밀번호를 모두 입력해주세요.');
		$errorBox.removeClass('hidden'); // 숨김 해제
		return;
	}

	$.ajax({
		type: 'POST',
		url: '/api/login',
		data: {
			id_give: id,
			pw_give: pw
		},
		success: function (response) {
			alert('로그인 성공!');
			// sessionStorage.setItem('mytoken', response['token']); // 토큰 세션 스토리지에 저장
			window.location.href = '/'; // index.html로 이동
		},
		error: function (xhr) {
			// 서버가 400, 401, 500 등 에러 코드를 보냈을 때
			// xhr.responseJSON 안에는 백엔드에서 보낸 {"result": "fail", "msg": "..."}

			let errorMessage = '서버와 통신 중 오류 발생'; // 기본 메시지

			if (xhr.responseJSON && xhr.responseJSON.msg) {
				errorMessage = xhr.responseJSON.msg; // "아이디/비밀번호가 올바르지 않습니다" 등
			}

			// 에러 박스에 메시지 띄우기
			$errorBox.text(errorMessage);
			$errorBox.removeClass('hidden');
		}
	});
}
