function scroll() {

  var signup = document.querySelector('.signup');

  if(signup) {

    var nav = document.querySelector('.nav');
    var threshold = nav ? nav.offsetHeight + nav.offsetTop : 0;

    if(scrollY > threshold) {

      signup.classList.add('signup--peekaboo');

    } else {

      signup.classList.remove('signup--peekaboo');

    }

  }

}

export { scroll };
